import asyncio
import spade
from spade import wait_until_finished
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from time import time
import random

from matplotlib import pyplot as plt

import numpy as np


# Количество агентов
N = 10
# Оценка диаметра графа (для настроек алгоритма)
d = N - 1

def get_adjacencies(num_nodes: int):
    """Сгенерировать произвольный связный неориентированный граф в виде списков смежности."""
    # Начнём с цепочки, чтобы гарантировать связность
    adj = [[] for _ in range(num_nodes)]
    for i in range(num_nodes - 1):
        adj[i].append(i + 2)
        adj[i + 1].append(i + 1)

    # Добавим случайные ребра для разнообразия
    extra = max(1, num_nodes // 2)
    for _ in range(extra):
        a = random.randrange(1, num_nodes + 1)
        b = random.randrange(1, num_nodes + 1)
        if a != b:
            if b not in adj[a - 1]:
                adj[a - 1].append(b)
            if a not in adj[b - 1]:
                adj[b - 1].append(a)

    # Сортируем списки смежности для стабильного вывода
    for lst in adj:
        lst.sort()

    return adj


def get_initial_values(num_nodes: int):
    """Сгенерировать начальные значения агентов (целые от 0 до 100)."""
    return [float(random.randint(0, 100)) for _ in range(num_nodes)]


initial_values = get_initial_values(N)
adjacencies = get_adjacencies(N)
max_iters = 100

messages_counter = 0


class SimpleAgent(Agent):
    class Waiting(CyclicBehaviour):
        async def receive_messages(self):
            """Получить сообщения от соседей (с таймаутом)."""
            self.control_value = 0.0
            counter = 0
            received_values = []
            conns = self.get("connections")
            while counter < len(conns):
                msg = await self.receive(timeout=0.3)
                if msg:
                    print(f"Agent {self.get('ID')}: Received message {msg.body}")
                    counter += 1
                    received_values.append(float(msg.body))
                else:
                    print(f"Agent {self.get('ID')}: Receiving messages timed out. Using partial information...")
                    counter += 1

            for value in received_values:
                self.control_value += (1.0 / 3.0) * (value - self.current_value)

        async def send_messages(self):
            """Отправить своё состояние соседям, с небольшим шумом."""
            for peer in self.get("connections"):
                noise = random.random() / 5.0 - 0.1
                msg = Message(to=f"{peer}@localhost")
                msg.body = str(self.current_value * (1.0 + noise))
                print(f"Agent {self.get('ID')}: Sending message to {peer}@localhost")
                self.msg_counter += 1
                await self.send(msg)

        async def on_start(self):
            self.current_value = self.get("number")
            self.values = [self.current_value]
            self.iteration = -1
            self.control_value = 0.0
            self.msg_counter = 0

        async def run(self):
            if self.iteration == -1:
                sleep_time = self.get("synced_time") - time()
                print(f"Agent {self.get('ID')} is waiting for others to start ({sleep_time, 2} sec)")
                await asyncio.sleep(sleep_time)
                print(f"Hello! I'm agent {self.get('ID')}. Connections: {self.get('connections')}")
                self.iteration = 1
                return

            stall = random.random()
            if stall < 0.95:
                print(f"Agent {self.get('ID')}: In the loop, iteration: {self.iteration}, current state: {self.current_value}")
                await self.send_messages()
                await self.receive_messages()
                self.current_value += self.control_value
            else:
                await asyncio.sleep(0.1)

            self.values.append(self.current_value)
            self.iteration += 1

            if self.iteration == max_iters:
                msg = Message(to="center@localhost")
                msg.body = str([self.values, self.msg_counter])
                await self.send(msg)
                await self.agent.stop()

    async def setup(self):
        wbhav = self.Waiting()
        self.add_behaviour(wbhav)

class CenterAgent(Agent):
    class ReceivingAverage(OneShotBehaviour):
        async def run(self):
            counter = 0
            values = []
            total_messages = 0
            while counter < N:
                msg = await self.receive(timeout=120)
                if msg:
                    # Печать сообщения центра красным цветом
                    print(f"\033[31mCenter received: {msg.body}\033[0m")
                    values.append(eval(msg.body))
                    counter += 1
                else:
                    print("Center did not receive any messages in set timeout")

            print("Center: Stopped receiving messages")

            average = np.zeros(len(values[0][0]))
            for i in range(N):
                total_messages += values[i][1]
                average += np.array(values[i][0])

            # Покажем два графика рядом: слева — состояния агентов, справа — среднее
            fig, axs = plt.subplots(1, 2, figsize=(14, 5))

            # Попробуем установить заголовок окна с графиком (если бэкенд поддерживает)
            try:
                mgr = plt.get_current_fig_manager()
                mgr.set_window_title("convergence plots")
            except Exception:
                try:
                    fig.canvas.manager.set_window_title("convergence plots")
                except Exception:
                    pass

            # Слева: состояния отдельных агентов
            for i in range(N):
                axs[0].plot(values[i][0], label=f"Agent {i + 1}")
            axs[0].set_title("Agent states")
            axs[0].set_xlabel("Iteration")
            axs[0].set_ylabel("Value")

            # Справа: среднее состояние по агентам
            axs[1].plot(average / N, color="tab:orange")
            axs[1].set_title("Average agent state")
            axs[1].set_xlabel("Iteration")
            axs[1].set_ylabel("Value")

            plt.tight_layout()
            plt.show()

            global messages_counter
            messages_counter = total_messages
            await self.agent.stop()

    async def setup(self):
        print("Center agent started up")
        bhav = self.ReceivingAverage()
        self.add_behaviour(bhav)



async def main():
    startup_time = 5
    synced_time = time() + startup_time

    agents = []
    for i in range(N):
        agents.append(SimpleAgent(f"{i+1}@localhost", "pass"))
        agents[i].set("ID", i + 1)
        agents[i].set("number", initial_values[i])
        agents[i].set("connections", adjacencies[i])
        agents[i].set("d", d)
        agents[i].set("synced_time", synced_time)
        await agents[i].start()

    center = CenterAgent("center@localhost", "pass")
    await center.start()
    await wait_until_finished(center)


if __name__ == "__main__":
    spade.run(main())
    # Печать фактического среднего красным цветом
    actual_avg = sum(initial_values) / float(N)
    print(f"\033[31mActual average: {actual_avg}\033[0m")
    print(f"Total messages: {messages_counter}")
    msg = messages_counter * 0.1
    ops = 2.1 * max_iters * 0.01
    mem = 2*N*(N+1) * 0.1
    cost = msg + ops + mem
    print(f"Cost = {cost}")
    
    