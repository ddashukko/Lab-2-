"""Перевірка: MongoDB і PostgreSQL повертають ОДНАКОВІ дані на однакові запити.

Без цього порівнювати швидкодію некоректно — можна випадково порівняти
запити, які повертають різний результат.
    python -m lab.verify
"""
import random
from datetime import datetime, timezone

from . import access as A
from .common import pg, mongo_db


def canon(x):
    """Приводимо дати до одного формату, щоб порівнювати значення, а не типи."""
    if isinstance(x, dict):
        return {k: canon(v) for k, v in x.items()}
    if isinstance(x, list):
        return [canon(v) for v in x]
    if isinstance(x, datetime):
        return x.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return x


def check(name, a, b):
    if canon(a) != canon(b):
        raise AssertionError(f"Розбіжність у {name}")


def main():
    conn, db = pg(autocommit=True), mongo_db()
    rng = random.Random(7)
    max_sid = conn.execute("SELECT MAX(Id) FROM Syllabuses").fetchone()[0]

    for sid in rng.sample(range(1, max_sid + 1), 40):
        ref = A.mongo_course(db, sid)
        check(f"курс {sid} (flat)", ref, A.pg_course_flat(conn, sid))
        check(f"курс {sid} (split)", ref, A.pg_course_split(conn, sid))
    print("R1 повний курс: 40 курсів — однаково")

    for q in [r[0] for r in conn.execute("SELECT MaterialId FROM Quizzes ORDER BY random() LIMIT 30")]:
        check(f"тест {q}", A.mongo_quiz_agg(db, q), A.pg_quiz(conn, q))
    print("R3 один тест: 30 тестів — однаково")

    for tag in ("t000", "t250"):
        key = lambda r: r["materialId"]
        m = sorted(A.mongo_tag_search(db, tag), key=key)
        check(f"тег {tag}", m, sorted(A.pg_tag_search(conn, tag), key=key))
        print(f"A1 тег {tag}: {len(m)} матеріалів — однаково")

    check("звіт по кафедрах", A.mongo_dept_stats(db), A.pg_dept_stats(conn))
    print("A2 звіт по кафедрах — однаково")
    print("УСІ ПЕРЕВІРКИ ПРОЙДЕНО")


if __name__ == "__main__":
    main()
