import simpy
import random
import statistics
from scipy.stats import truncnorm


# Вхідні дані
ORDER_RATE = 10  # середня кількість замовлень на годину (пуассонівський потік)
KITCHEN_CAPACITY = 2  # кількість замовлень, які кухня може готувати одночасно
COURIERS = 3  # кількість курʼєрів
COURIERS_SPEED = {"car": (15, 10), "scooter": (30, 10)}  # час доставки (середнє, розкид)
PREP_TIME = (15, 5)  # час приготування (середнє, розкид)
SIM_TIME = 240  # час симуляції (хвилини)

# Для статистики
waiting_times = []  # час простою замовлень у черзі
delivery_times = []  # загальний час виконання замовлень


# Функція обчислення нормального розподілу в чітких межах відхилення
def truncated_normal(mean, std_dev):
    lower_bound = mean - std_dev
    upper_bound = mean + std_dev

    # Обчислюємо межі як кількість стандартних відхилень від середнього значення
    a = (lower_bound - mean) / std_dev
    b = (upper_bound - mean) / std_dev

    # Використовуємо truncnorm.rvs для того, щоб вирахувати інтервал часу
    # за допомогою нормального розподілу але в межах lower_bound та upper_bound
    # a та b - межі у стандартному нормальному розподілі
    # loc - зміщення середнього значення (тобто де знаходиться центр розподілу).
    # scale розтягує розподіл так, щоб стандартне відхилення дорівнювало std_dev.
    return truncnorm.rvs(a, b, loc=mean, scale=std_dev)


# Обʼєкт Ресторану з доставкою
class Restaurant:
    def __init__(self, env):
        self.env = env
        self.kitchen = simpy.Resource(env, capacity=KITCHEN_CAPACITY) # двоканальна СМО
        self.couriers = simpy.Resource(env, capacity=COURIERS) # триканальна СМО

    # Функція генерування часу приготування замовлення
    def prepare_order(self):
        mean_time, std_dev = PREP_TIME
        prep_time = truncated_normal(mean_time, std_dev)
        yield self.env.timeout(prep_time)

    # Функція генерування часу доставки замовлення
    def deliver_order(self, transport):
        mean_time, std_dev = COURIERS_SPEED[transport]
        delivery_time = truncated_normal(mean_time, std_dev)
        yield self.env.timeout(delivery_time)


# Функція генерації замовлень (вимог)
def generate_orders(env, restaurant):
    order_id = 0
    arrival_times = []

    while True:
        # Інтервал між замовленнями (пуассонівський потік)
        arrival_time = random.expovariate(ORDER_RATE / 60)
        arrival_times.append(arrival_time)
        yield env.timeout(arrival_time)

        order_id += 1
        env.process(handle_order(env, restaurant, order_id))


# Мережа МО з двома підсистемами СМО
def handle_order(env, restaurant, order_id):
    arrival_time = env.now  # час, коли замовлення надійшло
    print(f"Order {order_id} arrives at {arrival_time:.2f} minutes")

    # Черга на кухню (двоканальна СМО1)
    with restaurant.kitchen.request() as request:
        # Замовлення очікує в черзу на приготування
        yield request

        # Замовлення завершило очікування в черзі
        prep_start = env.now
        waiting_times.append(prep_start - arrival_time) # записуємо час у черзі
        print(f"Order {order_id} starts preparation at {prep_start:.2f} minutes")

        # Початок приготування замовлення, очікуємо завершення приготування
        yield env.process(restaurant.prepare_order())

        # Приготування завершене
        prep_done = env.now
        print(f"Order {order_id} finished preparation at {prep_done:.2f} minutes")

    # Черга на доставку (триканальна СМО2 з двома каналами типу А та одним каналом типу В)
    with restaurant.couriers.request() as request:
        # Замовлення очікує в черзу на доставку
        yield request

        # Замовлення завершило очікування в черзі
        courier_start = env.now
        waiting_times.append(courier_start - arrival_time) # записуємо час у черзі
        print(f"Order {order_id} assigned to a courier at {courier_start:.2f} minutes")

        # Вибір транспортного засобу
        transport = "car" if random.random() < 2 / 3 else "scooter"
        # Початок доставки замовлення, очікуємо завершення доставки
        yield env.process(restaurant.deliver_order(transport))

        # Доставка завершена
        delivery_done = env.now
        print(f"Order {order_id} delivered at {delivery_done:.2f} minutes")
        # Записуємо загальний час виконання замовлення
        total_time = delivery_done - arrival_time
        delivery_times.append(total_time)


# Створюємо середовище симуляції
env = simpy.Environment()
restaurant = Restaurant(env)
env.process(generate_orders(env, restaurant))
env.run(until=SIM_TIME)

# Аналіз результатів
print("\n--- Simulation Results ---")
print(f"Середній час у черзі: {statistics.mean(waiting_times):.2f} хвилин")
print(f"Середній загальний час виконання замовлення: {statistics.mean(delivery_times):.2f} хвилин")
print(f"Максимальний час виконання замовлення: {max(delivery_times):.2f} хвилин")
print(f"Кількість замовлень: {len(delivery_times)}")