"""Тестування швидкодії MongoDB vs PostgreSQL.

    python -m lab.bench --scale S
    python -m lab.bench --scale L

Як міряємо:
  * дані однакові в обох БД (один генератор), індекси — еквівалентні;
  * у час входить отримання результату і перетворення його в Python-об'єкт,
    бо саме це потрібно застосунку;
  * перед замірами — прогрів (кілька запитів, які не рахуються);
  * 3 раунди, у кожному раунді змінюється порядок БД, щоб жодна не мала переваги;
  * ключі (id курсів, тестів) випадкові, але однакові для обох БД;
  * запис з однаковою надійністю: MongoDB {w:1, j:true} = PostgreSQL synchronous_commit=on;
  * рахуємо медіану (p50) і p95.
"""
import argparse
import gc
import json
import os
import random
import statistics
import time

from . import access as A
from . import datagen as g
from .common import pg, mongo_db, ROOT, SCALES, RECENT_SEMESTERS

ROUNDS = 3


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round((len(xs) - 1) * p / 100))]


def run(name, desc, impls, args, warmup, n, results, after_round=None):
    """impls: {назва: (функція, підключення)}. Кожна функція викликається з одним аргументом із args."""
    lat = {lb: [] for lb in impls}
    labels = list(impls)
    for r in range(ROUNDS):
        for lb in labels[r % len(labels):] + labels[:r % len(labels)]:   # зсув порядку
            fn, h = impls[lb]
            for a in args[:warmup]:
                fn(h, a)
            gc.disable()
            for a in args[warmup:warmup + n]:
                t0 = time.perf_counter()
                fn(h, a)
                lat[lb].append((time.perf_counter() - t0) * 1000)
            gc.enable()
            if after_round:
                after_round()
    results[name] = {"desc": desc, "impl": {
        lb: {"p50": pct(v, 50), "p95": pct(v, 95), "mean": statistics.fmean(v), "n": len(v)}
        for lb, v in lat.items()}}
    print(f"\n{name}: {desc}")
    for lb, s in results[name]["impl"].items():
        print(f"   {lb:38s} p50={s['p50']:9.3f} мс   p95={s['p95']:9.3f} мс   n={s['n']}")


def storage(conn, db):
    def pg_size(tables):
        return conn.execute("SELECT SUM(pg_table_size(c.oid))::bigint, SUM(pg_indexes_size(c.oid))::bigint "
                            "FROM pg_class c WHERE c.relname = ANY(%s)",
                            ([t.lower() for t in tables],)).fetchone()
    out = {}
    for key, tables, coll in (("course", [t for t, _ in g.COURSE_TABLES.values()], "course_content"),
                              ("attempts", [t for t, _ in g.ATTEMPT_TABLES.values()], "quiz_attempts")):
        d, i = pg_size(tables)
        st = db.command("collStats", coll)
        out[key] = {"pg_data": d, "pg_index": i, "mongo_data": st["storageSize"],
                    "mongo_index": st["totalIndexSize"]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="S", choices=SCALES)
    args = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, "results", f"load_{args.scale}.json")))
    conn = pg(autocommit=True)       # читання
    wconn = pg(autocommit=False)     # запис (явні транзакції)
    db = mongo_db()
    rng = random.Random(2024)
    max_sid = conn.execute("SELECT MAX(Id) FROM Syllabuses").fetchone()[0]
    results = {}

    # ---------- Читання ----------
    sids = [rng.randint(1, max_sid) for _ in range(500)]
    run("R1_full_course", "Відкрити курс цілком (модулі, матеріали, тести, рубрики)", {
        "MongoDB: findOne": (A.mongo_course, db),
        "PostgreSQL: 1 запит з JOIN": (A.pg_course_flat, conn),
        "PostgreSQL: 6 простих запитів": (A.pg_course_split, conn),
    }, sids, 50, 400, results)

    qids = [r[0] for r in conn.execute("SELECT MaterialId FROM Quizzes ORDER BY random() LIMIT 500")]
    run("R3_single_quiz", "Відкрити один тест за його id", {
        "MongoDB: aggregate": (A.mongo_quiz_agg, db),
        "PostgreSQL: 3 таблиці": (A.pg_quiz, conn),
    }, qids, 50, 400, results)

    # ---------- Запис ----------
    # W1: нові курси для нових силабусів (рядки Syllabuses створюємо заздалегідь, вони не входять у замір)
    K = 100
    new_sids = list(range(max_sid + 1, max_sid + 1 + K))
    with wconn.transaction():
        wconn.execute("DELETE FROM Topics WHERE SyllabusId > %s", (max_sid,))
        wconn.execute("DELETE FROM Syllabuses WHERE Id > %s", (max_sid,))
        for s in new_sids:
            wconn.execute("INSERT INTO Syllabuses (Id, DisciplineId, TeacherId, SemesterId) VALUES (%s,1,1,10)", (s,))
    db.course_content.delete_many({"_id": {"$gt": max_sid}})
    hdr = {k: v for k, v in A.mongo_course(db, 1).items() if k not in ("version", "updatedAt", "modules")}
    ids = g.Ids({k: v + 5_000_000 for k, v in meta["ids"].items()})
    new_docs = [g.make_course(random.Random(s), ids, {**hdr, "_id": s}) for s in new_sids]

    def cleanup_courses():
        db.course_content.delete_many({"_id": {"$gt": max_sid}})
        with wconn.transaction():
            wconn.execute("DELETE FROM Topics WHERE SyllabusId > %s", (max_sid,))
    run("W1_create_course", "Створити курс цілком", {
        "MongoDB: insertOne": (A.mongo_insert_course, db),
        "PostgreSQL: транзакція, 12 таблиць": (A.pg_insert_course, wconn),
    }, new_docs, 0, K, results, after_round=cleanup_courses)
    with wconn.transaction():
        wconn.execute("DELETE FROM Syllabuses WHERE Id > %s", (max_sid,))

    # W2: змінити бали одного питання
    upd = []
    for sid in rng.sample(range(1, max_sid + 1), 500):
        d = A.mongo_course(db, sid)
        quiz = next((m for mod in d["modules"] for m in mod["materials"] if m["type"] == "quiz"), None)
        if quiz:
            q = rng.choice(quiz["questions"])
            upd.append((sid, quiz["materialId"], q["questionId"], rng.randint(1, 5)))
    run("W2_update_question", "Змінити бали одного питання тесту", {
        "MongoDB: updateOne + arrayFilters": (A.mongo_update_question, db),
        "PostgreSQL: UPDATE 1 рядка": (A.pg_update_question, wconn),
    }, upd, 30, 300, results)

    # W4: записати спробу тесту
    base = meta["ids"]["attempt"]
    recent = list(db.course_content.find({"semesterId": {"$in": list(RECENT_SEMESTERS)}}).limit(200))
    quizzes = [(d, q) for d in recent for q in g.iter_quizzes(d)]
    aids = g.Ids({"attempt": base, "answer": meta["ids"]["answer"]})
    attempts = [g.make_attempt(rng, aids, *quizzes[i % len(quizzes)], rng.randint(1, meta["cfg"]["students"]))
                for i in range(500)]

    def cleanup_attempts():
        db.quiz_attempts.delete_many({"_id": {"$gt": base}})
        with wconn.transaction():
            wconn.execute("DELETE FROM QuizAttempts WHERE Id > %s", (base,))
    run("W4_insert_attempt", "Записати спробу тесту з усіма відповідями", {
        "MongoDB: insertOne": (A.mongo_insert_attempt, db),
        "PostgreSQL: транзакція, 3 таблиці": (A.pg_insert_attempt, wconn),
    }, attempts, 0, 500, results, after_round=cleanup_attempts)

    # W5: ціна денормалізації — у MongoDB ПІБ викладача скопійовано в кожен його курс
    ren = [(rng.randint(1, meta["cfg"]["teachers"]), f"Викладач {i}") for i in range(100)]
    run("W5_rename_teacher", "Змінити ПІБ викладача", {
        "MongoDB: updateMany (усі його курси)": (A.mongo_rename_teacher, db),
        "PostgreSQL: UPDATE 1 рядка Users": (A.pg_rename_teacher, wconn),
    }, ren, 5, 50, results)

    # ---------- Аналітика (по всіх курсах) ----------
    run("A1_tag_search", "Знайти всі матеріали з тегом t250 у всіх курсах", {
        "MongoDB: aggregate": (A.mongo_tag_search, db),
        "PostgreSQL: JOIN 5 таблиць": (A.pg_tag_search, conn),
    }, ["t250"] * 40, 1, 20, results)

    run("A2_dept_report", "Звіт по кафедрах: к-сть курсів, тестів, питань, години відео", {
        "MongoDB: aggregate": (lambda h, _: A.mongo_dept_stats(h), db),
        "PostgreSQL: GROUP BY": (lambda h, _: A.pg_dept_stats(h), conn),
    }, [None] * 10, 1, 4, results)

    results["S1_storage"] = storage(conn, db)
    print("\nРозмір на диску (байт):", json.dumps(results["S1_storage"], indent=1))

    out = os.path.join(ROOT, "results", f"bench_{args.scale}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print("Збережено", out)


if __name__ == "__main__":
    main()
