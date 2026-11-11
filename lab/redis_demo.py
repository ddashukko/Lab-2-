"""П.6 — Redis (key-value): базові запити на прикладах предметної області.

    python -m lab.redis_demo        -> друкує протокол і зберігає results/redis_demo.txt

Кожна команда виконується через redis-py як «сира» команда (execute_command),
тож у протоколі видно саме ту команду, яку можна ввести в redis-cli.
"""
import os
import random
import time

import redis

from .common import REDIS_URL, ROOT

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
LOG = []


def out(s=""):
    print(s)
    LOG.append(s)


def section(title):
    out()
    out("=" * 78)
    out(title)
    out("=" * 78)


def cmd(*args, note=None):
    res = r.execute_command(*args)
    shown = " ".join(str(a) if " " not in str(a) else f'"{a}"' for a in args)
    if len(shown) > 140:
        shown = shown[:137] + "..."
    out(f"> {shown}" + (f"      # {note}" if note else ""))
    txt = repr(res)
    out(f"  {txt if len(txt) < 300 else txt[:297] + '...'}")
    return res


def main():
    r.flushdb()
    section("1. STRING + TTL: сесії користувачів (вхід / вихід / автоматичне завершення)")
    token = "a1b2c3d4"
    cmd("SET", f"session:{token}", "user:15", "EX", 1800, "NX", note="NX — не перезаписати чужу сесію")
    cmd("GET", f"session:{token}", note="перевірка токена при кожному запиті")
    cmd("TTL", f"session:{token}", note="скільки секунд лишилось")
    cmd("EXPIRE", f"session:{token}", 1800, note="продовжити сесію (sliding expiration)")
    cmd("SET", "session:tmp", "user:16", "PX", 300)
    time.sleep(0.4)
    cmd("EXISTS", "session:tmp", note="ключ зник сам після 300 мс")
    cmd("DEL", f"session:{token}", note="logout")

    section("2. Лічильники (INCR — атомарні, без гонок)")
    cmd("INCR", "views:course:42", note="перегляд сторінки курсу")
    cmd("INCRBY", "views:course:42", 10)
    cmd("GET", "views:course:42")
    out("  Обмеження частоти входу (fixed window rate limit):")
    for _ in range(4):
        n = cmd("INCR", "ratelimit:login:10.0.0.7")
        if n == 1:
            cmd("EXPIRE", "ratelimit:login:10.0.0.7", 60)
    out("  -> застосунок блокує вхід, якщо значення > 3")

    section("3. HASH: картка студента (кеш профілю з PostgreSQL)")
    cmd("HSET", "student:15", "fullName", "Янчук Дарія", "group", "ТК-31", "studyForm", "Budget", "avgGrade", "91.5")
    cmd("HGET", "student:15", "group")
    cmd("HMGET", "student:15", "fullName", "avgGrade")
    cmd("HINCRBYFLOAT", "student:15", "avgGrade", 0.25)
    cmd("HGETALL", "student:15")
    cmd("HDEL", "student:15", "studyForm")
    cmd("HEXISTS", "student:15", "studyForm")

    section("4. LIST: стрічка сповіщень і черга перевірки робіт")
    for msg in ["Нова оцінка: БД — 95", "Змінено аудиторію: пара 3", "Новий тест у курсі 42"]:
        cmd("LPUSH", "notif:user:15", msg)
    cmd("LTRIM", "notif:user:15", 0, 49, note="зберігаємо лише 50 останніх")
    cmd("LRANGE", "notif:user:15", 0, 1, note="2 найновіші")
    cmd("LLEN", "notif:user:15")
    cmd("RPUSH", "queue:grading", "attempt:1001", "attempt:1002", "attempt:1003", note="продюсер")
    cmd("LPOP", "queue:grading", note="воркер забирає задачу (FIFO)")
    cmd("BLPOP", "queue:grading", 1, note="блокуюче очікування задачі")

    section("5. SET: хто онлайн на занятті (множини та операції над ними)")
    cmd("SADD", "online:lesson:1001", 15, 16, 17, 18, 21)
    cmd("SADD", "online:lesson:1002", 15, 17, 22)
    cmd("SADD", "group:ТК-31", 15, 16, 17, 18, 19, 20, 21, 22)
    cmd("SISMEMBER", "online:lesson:1001", 19, note="чи присутній студент 19")
    cmd("SCARD", "online:lesson:1001")
    cmd("SINTER", "online:lesson:1001", "online:lesson:1002", note="були на обох заняттях")
    cmd("SDIFF", "group:ТК-31", "online:lesson:1001", note="відсутні на занятті 1001")
    cmd("SUNION", "online:lesson:1001", "online:lesson:1002")

    section("6. SORTED SET: рейтинг студентів за тестом")
    rng = random.Random(1)
    scores = {f"student:{i}": rng.randint(5, 30) for i in range(10, 25)}
    args = [x for k, v in scores.items() for x in (v, k)]
    cmd("ZADD", "leaderboard:quiz:12345", *args)
    cmd("ZINCRBY", "leaderboard:quiz:12345", 3, "student:15", note="перерахунок після апеляції")
    cmd("ZREVRANGE", "leaderboard:quiz:12345", 0, 4, "WITHSCORES", note="топ-5")
    cmd("ZREVRANK", "leaderboard:quiz:12345", "student:15", note="місце студента (з 0)")
    cmd("ZSCORE", "leaderboard:quiz:12345", "student:15")
    cmd("ZRANGEBYSCORE", "leaderboard:quiz:12345", "-inf", "(18", note="не склали (поріг 18)")
    cmd("ZCOUNT", "leaderboard:quiz:12345", 18, "+inf", note="скільки склали")

    section("7. Транзакція MULTI/EXEC: зарахування спроби тесту атомарно")
    p = r.pipeline(transaction=True)
    p.zadd("leaderboard:quiz:12345", {"student:30": 27})
    p.incr("attempts:quiz:12345")
    p.lpush("notif:user:30", "Тест 12345: 27 балів")
    res = p.execute()
    out("> MULTI; ZADD leaderboard:quiz:12345 27 student:30; INCR attempts:quiz:12345; "
        "LPUSH notif:user:30 ...; EXEC")
    out(f"  {res}")
    section("8. Службові команди")
    cmd("SCAN", 0, "MATCH", "leaderboard:*", "COUNT", 1000, note="а не KEYS * — не блокує сервер")
    cmd("TYPE", "leaderboard:quiz:12345")
    cmd("TYPE", "student:15")
    cmd("DBSIZE")
    mem = r.info("memory")
    out(f"> INFO memory  ->  used_memory_human={mem['used_memory_human']}")

    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "redis_demo.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))


if __name__ == "__main__":
    main()
