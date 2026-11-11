"""Створює схеми та завантажує однакові дані в PostgreSQL і MongoDB.

    python -m lab.load --scale S      # ~2 000 курсів
    python -m lab.load --scale L      # ~20 000 курсів

Час масового завантаження кожної БД вимірюється окремо
і зберігається в results/load_<scale>.json.
"""
import argparse
import json
import os
import random
import subprocess
import time

from . import datagen as g
from .common import pg, mongo_db, SCALES, SEMESTERS, RECENT_SEMESTERS, ROOT, MONGO_URI

FIRST = ["Олександр", "Марія", "Іван", "Олена", "Андрій", "Наталія", "Сергій", "Ірина", "Дмитро",
         "Тетяна", "Віктор", "Оксана", "Юрій", "Світлана", "Богдан", "Дарія", "Максим", "Софія"]
LAST = ["Шевченко", "Коваленко", "Бондаренко", "Ткаченко", "Кравченко", "Олійник", "Мельник",
        "Лисенко", "Савченко", "Руденко", "Мороз", "Кузьменко", "Петренко", "Гончаренко", "Янчук"]

BATCH = 500


def run_sql(conn, fname):
    with open(os.path.join(ROOT, "sql", fname), encoding="utf-8") as f:
        conn.execute(f.read())
    conn.commit()


def mongosh(fname):
    subprocess.run(["mongosh", "--quiet", MONGO_URI + "/lms", os.path.join(ROOT, "mongo", fname)], check=True)


def copy_rows(cur, table, cols, rows):
    if not rows:
        return
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row(r)


def load_base(conn, rng, cfg):
    """Реляційна частина, яка залишається в PostgreSQL в обох варіантах."""
    cur = conn.cursor()
    deps = [(i, f"Кафедра {g.text(rng, 1, 3)}", f"K{i:02d}") for i in range(1, cfg["departments"] + 1)]
    copy_rows(cur, "Departments", ["Id", "Name", "ShortName"], deps)

    users, teachers, students = [], [], []
    uid = 1
    users.append((uid, "admin@lms.example", "Адміністратор", "x", "Admin"))
    for t in range(1, cfg["teachers"] + 1):
        uid += 1
        users.append((uid, f"teacher{t}@lms.example", f"{rng.choice(LAST)} {rng.choice(FIRST)}", "x", "Teacher"))
        teachers.append((t, uid, rng.randint(1, cfg["departments"]), "Доцент", "к.т.н."))
    groups = [(i, f"ГР-{i:03d}", 2021 + i % 5, rng.randint(1, cfg["departments"])) for i in range(1, cfg["groups"] + 1)]
    for s in range(1, cfg["students"] + 1):
        uid += 1
        users.append((uid, f"student{s}@lms.example", f"{rng.choice(LAST)} {rng.choice(FIRST)}", "x", "Student"))
        students.append((s, uid, rng.randint(1, cfg["groups"]), f"RB{s:06d}", "Budget"))
    copy_rows(cur, "Users", ["Id", "Email", "FullName", "PasswordHash", "Role"], users)
    copy_rows(cur, "Teachers", ["Id", "UserId", "DepartmentId", "Position", "Degree"], teachers)
    copy_rows(cur, "AcademicGroups", ["Id", "Name", "EntryYear", "DepartmentId"], groups)
    copy_rows(cur, "Students", ["Id", "UserId", "GroupId", "RecordBookNumber", "StudyForm"], students)
    discs = [(i, g.sentence(rng, 2, 4), f"D{i:04d}") for i in range(1, cfg["disciplines"] + 1)]
    copy_rows(cur, "Disciplines", ["Id", "Name", "Code"], discs)
    copy_rows(cur, "Semesters", ["Id", "AcademicYear", "Number"],
              [(i + 1, y, n) for i, (y, n) in enumerate(SEMESTERS)])
    copy_rows(cur, "ClassTypes", ["Id", "Name"], [(1, "Лекція"), (2, "Практика"), (3, "Лабораторна")])

    syl = []
    for sid in range(1, cfg["syllabuses"] + 1):
        syl.append((sid, rng.randint(1, cfg["disciplines"]), rng.randint(1, cfg["teachers"]),
                    rng.randint(1, len(SEMESTERS)), g.sentence(rng, 10, 30)))
    copy_rows(cur, "Syllabuses", ["Id", "DisciplineId", "TeacherId", "SemesterId", "Description"], syl)
    conn.commit()

    # Заголовки документів (денормалізовані поля) беремо з БД — як це робив би застосунок
    cur.execute("""
        SELECT s.Id, d.Id, d.Code, d.Name, t.Id, u.FullName, dep.Id, dep.ShortName,
               sem.Id, sem.AcademicYear, sem.Number
        FROM Syllabuses s
        JOIN Disciplines d ON d.Id = s.DisciplineId
        JOIN Teachers t ON t.Id = s.TeacherId JOIN Users u ON u.Id = t.UserId
        JOIN Departments dep ON dep.Id = t.DepartmentId
        JOIN Semesters sem ON sem.Id = s.SemesterId ORDER BY s.Id""")
    keys = ["_id", "disciplineId", "disciplineCode", "disciplineName", "teacherId", "teacherName",
            "departmentId", "departmentShortName", "semesterId", "academicYear", "semesterNo"]
    return [dict(zip(keys, r)) for r in cur.fetchall()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="S", choices=SCALES)
    args = ap.parse_args()
    cfg = SCALES[args.scale]
    rng = random.Random(42)
    ids = g.Ids()

    conn = pg()
    run_sql(conn, "01_base_schema.sql")
    run_sql(conn, "02_course_content.sql")
    mongosh("setup.js")
    mdb = mongo_db()

    headers = load_base(conn, rng, cfg)
    t = {"pg": 0.0, "mongo": 0.0, "pg_attempts": 0.0, "mongo_attempts": 0.0}
    counts = {"courses": 0, "attempts": 0}
    cur = conn.cursor()
    student_count = cfg["students"]

    for b in range(0, len(headers), BATCH):
        docs = [g.make_course(rng, ids, h) for h in headers[b:b + BATCH]]
        attempts = []
        for d in docs:
            if d["semesterId"] in RECENT_SEMESTERS:
                for q in g.iter_quizzes(d):
                    for st in rng.sample(range(1, student_count + 1), cfg["attempts_per_quiz"]):
                        attempts.append(g.make_attempt(rng, ids, d, q, st))
        # --- PostgreSQL: COPY у 12 таблиць + версія контенту в Syllabuses ---
        rows = {k: [] for k in g.COURSE_TABLES}
        for d in docs:
            g.doc_to_rows(d, rows)
        t0 = time.perf_counter()
        for k, (table, cols) in g.COURSE_TABLES.items():
            copy_rows(cur, table, cols, rows[k])
        cur.executemany("UPDATE Syllabuses SET ContentVersion = %s, ContentUpdatedAt = %s WHERE Id = %s",
                        [(d["version"], d["updatedAt"], d["_id"]) for d in docs])
        conn.commit()
        t["pg"] += time.perf_counter() - t0
        # --- MongoDB ---
        t0 = time.perf_counter()
        mdb.course_content.insert_many(docs, ordered=False)
        t["mongo"] += time.perf_counter() - t0
        # --- Спроби тестів ---
        if attempts:
            arows = {k: [] for k in g.ATTEMPT_TABLES}
            for a in attempts:
                g.attempt_to_rows(a, arows)
            t0 = time.perf_counter()
            for k, (table, cols) in g.ATTEMPT_TABLES.items():
                copy_rows(cur, table, cols, arows[k])
            conn.commit()
            t["pg_attempts"] += time.perf_counter() - t0
            mdocs = [g.mongo_attempt(a) for a in attempts]
            t0 = time.perf_counter()
            mdb.quiz_attempts.insert_many(mdocs, ordered=False)
            t["mongo_attempts"] += time.perf_counter() - t0
        counts["courses"] += len(docs)
        counts["attempts"] += len(attempts)
        print(f"  {counts['courses']}/{len(headers)} courses, {counts['attempts']} attempts", flush=True)

    # Індекси після завантаження (час теж міряємо)
    t0 = time.perf_counter()
    run_sql(conn, "03_indexes.sql")
    t["pg_indexes"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    mongosh("indexes.js")
    t["mongo_indexes"] = time.perf_counter() - t0
    # Синхронізуємо послідовності SERIAL з явно вставленими ID
    conn.autocommit = True
    for table in ["Users", "Departments", "Teachers", "AcademicGroups", "Students", "Disciplines",
                  "Semesters", "Syllabuses", "Topics", "Materials", "QuizQuestions", "QuizOptions",
                  "AssignmentRubric", "QuizAttempts", "AttemptAnswers", "ClassTypes"]:
        conn.execute(f"SELECT setval(pg_get_serial_sequence('{table.lower()}', 'id'), "
                     f"(SELECT COALESCE(MAX(Id), 1) FROM {table}))")
    conn.execute("VACUUM ANALYZE")

    meta = {"scale": args.scale, "cfg": cfg, "load_seconds": t, "counts": counts,
            "ids": vars(ids)}
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", f"load_{args.scale}.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
