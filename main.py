import simpy
import random
import statistics
from scipy.stats import truncnorm


# Вхідні дані
ORDER_RATE = 10  # середня кількість замовлень на годину (пуассонівський потік)
KITCHEN_CAPACITY = 2  # кількість замовлень, які кухня може готувати одночасно
PREP_TIME = (20, 5)  # час приготування (середнє, розкид)
COURIERS = {
    "car": {
        "speed": (20, 10), # час доставки (середнє, розкид)
        "capacity": 1, # кількість курʼєрів з даним видом транспорту
        "in_use": 0
    },
    "scooter": {
        "speed": (36, 10), # час доставки (середнє, розкид)
        "capacity": 1, # кількість курʼєрів з даним видом транспорту
        "in_use": 0
    }
}
SIM_TIME = 480  # час симуляції (хвилини)

# Для статистики
prep_waiting_times = []  # час простою замовлень у черзі на приготування
delivery_waiting_times = [] # час простою замовлень у черзі на доставку
order_complete_times = []  # загальний час виконання замовлень
prep_queue_lengths = [] # довжина черги на приготування
delivery_queue_lengths = [] # довжина черги на доставку


# Функція обчислення нормального розподілу в чітких межах відхилення
def truncated_normal(mean: int, std_dev: int):
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
    def __init__(self, env: simpy.Environment):
        self.env = env
        # ресурси
        self.kitchen = simpy.Resource(env, capacity=KITCHEN_CAPACITY) # кухня з ємністю 2
        self.couriers = simpy.Resource(env, capacity=sum(courier['capacity'] for courier in COURIERS.values())) # два курʼєри
        # допоміжні дані для відслідковування завантаженості різних типів курʼєрів
        # та для вибору типу курʼєра для доставки за доступністю
        self.courier_assignments = COURIERS.copy()

    # Функція генерування часу приготування замовлення
    def prepare_order(self):
        mean_time, std_dev = PREP_TIME
        prep_time = truncated_normal(mean_time, std_dev)
        yield self.env.timeout(prep_time)

    # Функція генерування часу доставки замовлення
    def deliver_order(self, transport: str):
        mean_time, std_dev = COURIERS[transport]["speed"]
        delivery_time = truncated_normal(mean_time, std_dev)
        yield self.env.timeout(delivery_time)

    # Функція призначення замовлення доступному типу курʼєра
    def assign_courier(self):
        car_couriers_available = self.courier_assignments["car"]["in_use"] < \
            self.courier_assignments["car"]["capacity"]
        scooter_couriers_available = self.courier_assignments["scooter"]["in_use"] < \
            self.courier_assignments["scooter"]["capacity"]
        print(f"car couriers: in use {self.courier_assignments['car']['in_use']}, available - {car_couriers_available}")
        print(f"scooter couriers: in use {self.courier_assignments['scooter']['in_use']}, available - {scooter_couriers_available}")
        if car_couriers_available and scooter_couriers_available:
            transport = "car"
            self.courier_assignments["car"]["in_use"] += 1
        elif not car_couriers_available:
            transport = "scooter"
            self.courier_assignments["scooter"]["in_use"] += 1
        else: # спрацьовує тільки тоді коли зайняті усі курʼєри на електроскутерах
            transport = "car"
            self.courier_assignments["car"]["in_use"] += 1
        return transport
    
    # Функція скасування призначення замовлення певному типу курʼєра
    def deassign_courier(self, transport: str):
        self.courier_assignments[transport]["in_use"] -= 1


# Функція генерації замовлень (вимог)
def generate_orders(env: simpy.Environment, restaurant: Restaurant):
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
def handle_order(env: simpy.Environment, restaurant: Restaurant, order_id: int):
    arrival_time = env.now  # час, коли замовлення надійшло
    print(f"Order {order_id} arrives at {arrival_time:.2f} minutes")

    # Черга на кухню (двоканальна СМО1)
    with restaurant.kitchen.request() as request:
        # Замовлення очікує в черзу на приготування
        prep_queue_lengths.append(len(restaurant.kitchen.queue))  # записуємо кількість у черзі
        yield request

        # Замовлення завершило очікування в черзі
        prep_start = env.now
        prep_waiting_times.append(prep_start - arrival_time) # записуємо час у черзі
        print(f"Order {order_id} starts preparation at {prep_start:.2f} minutes")

        # Початок приготування замовлення, очікуємо завершення приготування
        yield env.process(restaurant.prepare_order())

        # Приготування завершене
        prep_done = env.now
        print(f"Order {order_id} finished preparation at {prep_done:.2f} minutes")

    # Черга на доставку (двоканальна СМО2 з одним каналом типу А та одним каналом типу В)
    with restaurant.couriers.request() as request:
        # Замовлення очікує в черзі на доставку
        delivery_queue_lengths.append(len(restaurant.couriers.queue))  # записуємо кількість у черзі
        yield request

        # Замовлення завершило очікування в черзі

        # Призначаємо замовлення курʼєру
        # Якщо обидва типи курʼєрів вільні, то обирається курʼєр з машиною
        transport = restaurant.assign_courier()

        courier_start = env.now
        delivery_waiting_times.append(courier_start - prep_done) # записуємо час у черзі
        print(f"Order {order_id} assigned to a courier on {transport} at {courier_start:.2f} minutes")

        # Початок доставки замовлення, очікуємо завершення доставки
        yield env.process(restaurant.deliver_order(transport))

        # Доставка завершена
        restaurant.deassign_courier(transport)
        
        delivery_done = env.now
        print(f"Order {order_id} delivered with {transport} at {delivery_done:.2f} minutes")
        # Записуємо загальний час виконання замовлення
        total_time = delivery_done - arrival_time
        order_complete_times.append(total_time)


# Створюємо середовище симуляції
env = simpy.Environment()
restaurant = Restaurant(env)
env.process(generate_orders(env, restaurant))
env.run(until=SIM_TIME)

# Аналіз результатів
print("\n--- Simulation Results ---")
print(f"Середній час у черзі на приготування: {statistics.mean(prep_waiting_times):.1f} хвилин")
print(f"Середній час у черзі на доставку: {statistics.mean(delivery_waiting_times):.1f} хвилин")
print(f"Загальний середній час у чергах: {statistics.mean(prep_waiting_times + delivery_waiting_times):.1f} хвилин")
print(f"Середня кількість замовлень у черзі на приготування: {statistics.mean(prep_queue_lengths):.1f}")
print(f"Середня кількість замовлень у черзі на доставку: {statistics.mean(delivery_queue_lengths):.1f}")
print(f"Загальна середня кількість замовлень у чергах: {statistics.mean(prep_queue_lengths + delivery_queue_lengths):.1f}")
print(f"Загальний середній час виконання замовлень: {statistics.mean(order_complete_times):.1f} хвилин")
print(f"Кількість виконаних замовлень: {len(order_complete_times)}")

# print()
# print(max(prep_waiting_times), prep_waiting_times.index(max(prep_waiting_times)))
# print(max(delivery_waiting_times), delivery_waiting_times.index(max(delivery_waiting_times)))
