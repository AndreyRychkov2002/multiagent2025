import asyncio
import spade
from spade import wait_until_finished
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from time import time
import random


def get_adjacencies(N):
    """
    Возвращает список смежности для фиксированного связного графа на N вершинах.
    Реализация: кольцо (каждая вершина связана с соседями) + несколько дополнительных ребер
    для большей связности. Нумерация вершин — от 1 до N (включительно).
    """
    if N <= 1:
        return [[] for _ in range(N)]

    adjacencies = []
    for i in range(N):
        # добавляем соседей по кольцу
        neighbours = {((i - 1) % N) + 1, ((i + 1) % N) + 1}

        # добавляем дополнительные ребра для разнообразия структуры
        # например, для каждых трех вершин добавим ребро на +3 позицию
        if N >= 4 and i % 3 == 0:
            neighbours.add(((i + 3) % N) + 1)

        # для некоторой вариативности добавим ребро к первой вершине
        if i % 5 == 0 and i != 0:
            neighbours.add(1)

        # удаляем петли и сортируем список соседей
        neighbours.discard(i + 1)
        adjacencies.append(sorted(neighbours))

    return adjacencies

def get_values(N):
    """Возвращает список случайных чисел (1..99) длины N, использует модуль random."""
    return [random.randint(1, 99) for _ in range(N)]

N = 10 # Число агентов
d = N - 1 # Максимальный возможный диаметр связного графа на N вершинах

values = get_values(N)
adjacencies = get_adjacencies(N)


class SimpleAgent(Agent):
    class Waiting(CyclicBehaviour):
        """
        Получаем и отправляем сообщения всем соседям в течение d итераций.
        В каждом сообщении содержится словарь известных агенту пар (ID агента: число).
        В конце, агент с наибольшим ID отправляет в центр среднее значение всех полученных им чисел.
        """
        async def receive_messages(self):
            """Ожидаем сообщения от всех соседей и объединяем словари."""
            cnt = 0
            while cnt < len(self.get("connections")):
                msg = await self.receive(timeout=10)
                if msg:
                    # Выводим идентификатор агента и полученное тело сообщения
                    print(f"Agent {self.get('ID')}: Received message {msg.body}")
                    cnt += 1
                    msg_dict = eval(msg.body)
                    msg_keys = msg_dict.keys()
                    cur_keys = self.values.keys()
                    for key in msg_keys:
                        if key not in cur_keys:
                            self.values[key] = msg_dict[key]
                else:
                    print(f"Agent {self.get('ID')}: Receiving messages timed out")

        async def send_messages(self):
            for id in self.get("connections"): # Отправляем сообщение всем соседям
                msg = Message(to=f"{id}@localhost")
                msg.body = str(self.values)
                print(f"Agent {self.get('ID')}: Sending message to {id}@localhost")
                await self.send(msg)

        async def on_start(self):
            self.iteration = None
            self.values = {self.get("ID"): self.get("number")}

        async def run(self):
            if self.iteration is None:
                sleep_time = self.get("synced_time") - time()
                print(
                    f"Agent {self.get('ID')} is waiting for others to start {sleep_time} sec)"
                )
                await asyncio.sleep(sleep_time)
                print(
                    f"Hello World! I'm agent {self.get('ID')}. Connections: {self.get('connections')}"
                )
                self.iteration = 1
            else:
                print(f"Agent {self.get('ID')}: In the loop, iteration: {self.iteration}, current state: {self.values}")
                await self.send_messages()  # отправляем свои известные данные соседям
                await self.receive_messages()  # получаем данные от соседей
                self.iteration += 1
                
            
            if self.iteration == self.get("d"):  # Все возможные соседи уже должны были передать свои данные
                if max(self.values.keys()) == self.get("ID"):
                    msg = Message(to="center@localhost")
                    avg = 0
                    for key in self.values.keys():
                        avg += self.values[key]
                    msg.body = f"From Agent {self.get('ID')}: Average: {avg / len(self.values.keys())}"
                    await self.send(msg)
                await self.agent.stop()


    async def setup(self):
        self.add_behaviour(self.Waiting())

class CenterAgent(Agent):
    class ReceivingAverage(OneShotBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg:
                print(f"\033[31mCenter received: {msg.body}\033[0m") # Печатаем красным цветом
            else:
                print("Center did not receive any messages in set timeout")
            print("Center: Stopped receiving messages")
            await self.agent.stop()
    
    async def setup(self):
        print("Center agent started up")
        bhav = self.ReceivingAverage()
        self.add_behaviour(bhav)



async def main():
    startup_time = 10
    synced_time = time() + startup_time

    agents = []
    for i in range(N):
        agents.append(SimpleAgent(f"{str(i + 1)}@localhost", "pass"))
        agents[i].set("ID", i+1)
        agents[i].set("number", values[i])
        agents[i].set("connections", adjacencies[i])
        agents[i].set("d", d)
        agents[i].set("synced_time", synced_time)
        await agents[i].start()

    center = CenterAgent("center@localhost", "pass")
    await center.start()
    await wait_until_finished(center)


if __name__ == "__main__":
    spade.run(main())
    print(f"\033[31mActual average: {sum(values) / N}\033[0m")
    total_connections = sum(len(x) for x in adjacencies)
    msgs = 2 * total_connections * d
    ops = 41 * N * (N - 1) + N
    mem = N * (N - 1) + 2 * N * N + 4
    cost = 1000 + msgs * 0.1 + ops * 0.01 + mem * 0.1
    print(f"Vertecies: {N}")
    print(f"Edges: {total_connections}")
    print(f"Cost = {cost}")
