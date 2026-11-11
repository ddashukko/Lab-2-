import os
import psycopg
from pymongo import MongoClient, WriteConcern

PG_DSN = os.environ.get("PG_DSN", "host=localhost dbname=lms user=postgres password=postgres")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pg(autocommit=False):
    return psycopg.connect(PG_DSN, autocommit=autocommit)


def mongo_db():
    # tz_aware=True: дати повертаються як datetime з UTC — так само, як timestamptz у psycopg.
    # Write concern {w:1, j:true}: підтвердження після запису в журнал на диск —
    # еквівалент synchronous_commit=on у PostgreSQL (чесне порівняння запису).
    client = MongoClient(MONGO_URI, tz_aware=True)
    return client.get_database("lms", write_concern=WriteConcern(w=1, j=True))


SCALES = {
    # S — одна кафедра/факультет; L — університет з архівом за 5 років
    "S": dict(departments=10, teachers=150, groups=60, students=1500, disciplines=300,
              syllabuses=2000, attempts_per_quiz=15),
    "L": dict(departments=20, teachers=600, groups=300, students=9000, disciplines=1500,
              syllabuses=20000, attempts_per_quiz=15),
}
SEMESTERS = [(f"{y}/{y + 1}", n) for y in range(2021, 2026) for n in (1, 2)]  # 10 семестрів
RECENT_SEMESTERS = {9, 10}  # спроби тестів є лише для курсів поточного навчального року
