"""Однакові за змістом операції для MongoDB і PostgreSQL.

Кожна функція повертає результат у тій самій формі (dict/list), який
потрібен застосунку, тож у вимірювання входить і десеріалізація/збирання
об'єкта на клієнті — так, як це відбувалося б у реальному бекенді.
"""
from datetime import datetime, timezone

from . import datagen as g

# =====================================================================
# R1. Повний курс (сторінка курсу у студента / редактор у викладача)
# =====================================================================

def mongo_course(db, sid):
    return db.course_content.find_one({"_id": sid})


HEADER_SQL = """
    SELECT s.Id, d.Id, d.Code, d.Name, t.Id, u.FullName, dep.Id, dep.ShortName,
           sem.Id, sem.AcademicYear, sem.Number, s.ContentVersion, s.ContentUpdatedAt
    FROM Syllabuses s
    JOIN Disciplines d   ON d.Id = s.DisciplineId
    JOIN Teachers t      ON t.Id = s.TeacherId
    JOIN Users u         ON u.Id = t.UserId
    JOIN Departments dep ON dep.Id = t.DepartmentId
    JOIN Semesters sem   ON sem.Id = s.SemesterId"""
HEADER_KEYS = ["_id", "disciplineId", "disciplineCode", "disciplineName", "teacherId", "teacherName",
               "departmentId", "departmentShortName", "semesterId", "academicYear", "semesterNo",
               "version", "updatedAt"]


def _material(r):
    """r: (id, orderNo, type, title, isRequired, tags, body, readingTime, vUrl, dur, fUrl, fmt, size,
            lUrl, timeLimit, attempts, passing, deadline, maxPoints)"""
    (mid, on, t, title, req, tags, body, rt, vurl, dur, furl, fmt, size, lurl,
     tl, att, ps, dl, mp) = r
    m = {"materialId": mid, "orderNo": on, "type": t, "title": title, "isRequired": req,
         "tags": tags or []}
    if t == "lecture":
        m["body"] = body; m["readingTimeMin"] = rt
    elif t == "video":
        m["url"] = vurl; m["durationSec"] = dur
    elif t == "file":
        m["url"] = furl; m["format"] = fmt; m["sizeKb"] = size
    elif t == "link":
        m["url"] = lurl
    elif t == "quiz":
        m["timeLimitMin"] = tl; m["attemptsAllowed"] = att; m["passingScore"] = ps
        m["questions"] = []
    elif t == "assignment":
        m["deadline"] = dl; m["maxPoints"] = mp; m["rubric"] = []
    return m


MATERIAL_COLS = """m.Id, m.OrderNo, m.Type, m.Title, m.IsRequired,
       (SELECT array_agg(mt.Tag ORDER BY mt.Tag) FROM MaterialTags mt WHERE mt.MaterialId = m.Id),
       ml.Body, ml.ReadingTimeMin, mv.Url, mv.DurationSec, mf.Url, mf.Format, mf.SizeKb, mk.Url,
       qz.TimeLimitMin, qz.AttemptsAllowed, qz.PassingScore, a.Deadline, a.MaxPoints"""
MATERIAL_JOINS = """
    LEFT JOIN MaterialLectures ml ON ml.MaterialId = m.Id
    LEFT JOIN MaterialVideos mv   ON mv.MaterialId = m.Id
    LEFT JOIN MaterialFiles mf    ON mf.MaterialId = m.Id
    LEFT JOIN MaterialLinks mk    ON mk.MaterialId = m.Id
    LEFT JOIN Quizzes qz          ON qz.MaterialId = m.Id
    LEFT JOIN Assignments a       ON a.MaterialId = m.Id"""

# --- Стратегія A: один великий запит з LEFT JOIN по всіх 12 таблицях ----
FLAT_SQL = f"""
    SELECT tp.Id, tp.OrderNo, tp.Title, tp.Hours, {MATERIAL_COLS},
           qq.Id, qq.OrderNo, qq.Text, qq.QType, qq.Points,
           qo.Id, qo.OrderNo, qo.Text, qo.IsCorrect,
           r.Id, r.OrderNo, r.Criterion, r.Points
    FROM Topics tp
    JOIN Materials m ON m.TopicId = tp.Id
    {MATERIAL_JOINS}
    LEFT JOIN QuizQuestions qq    ON qq.QuizId = qz.MaterialId
    LEFT JOIN QuizOptions qo      ON qo.QuestionId = qq.Id
    LEFT JOIN AssignmentRubric r  ON r.AssignmentId = a.MaterialId
    WHERE tp.SyllabusId = %s
    ORDER BY tp.OrderNo, m.OrderNo, qq.OrderNo, qo.OrderNo, r.OrderNo"""


def pg_course_flat(conn, sid):
    cur = conn.cursor()
    h = cur.execute(HEADER_SQL + " WHERE s.Id = %s", (sid,)).fetchone()
    doc = dict(zip(HEADER_KEYS, h))
    modules, mods, mats, qs = [], {}, {}, {}
    for r in cur.execute(FLAT_SQL, (sid,)):
        tid = r[0]
        mod = mods.get(tid)
        if mod is None:
            mod = mods[tid] = {"topicId": tid, "orderNo": r[1], "title": r[2], "hours": r[3], "materials": []}
            modules.append(mod)
        mid = r[4]
        m = mats.get(mid)
        if m is None:
            m = mats[mid] = _material(r[4:23])
            mod["materials"].append(m)
        if r[23] is not None:                       # питання тесту
            q = qs.get(r[23])
            if q is None:
                q = qs[r[23]] = {"questionId": r[23], "orderNo": r[24], "text": r[25], "qtype": r[26],
                                 "points": r[27], "options": []}
                m["questions"].append(q)
            if r[28] is not None:
                q["options"].append({"optionId": r[28], "orderNo": r[29], "text": r[30], "isCorrect": r[31]})
        if r[32] is not None:                       # критерій рубрики
            m["rubric"].append({"criterionId": r[32], "orderNo": r[33], "criterion": r[34], "points": r[35]})
    doc["modules"] = modules
    return doc


# --- Стратегія B: окремий запит на кожен рівень (як EF Core AsSplitQuery) --
SPLIT_TOPICS = "SELECT Id, OrderNo, Title, Hours FROM Topics WHERE SyllabusId = %s ORDER BY OrderNo"
SPLIT_MATERIALS = f"""SELECT m.TopicId, {MATERIAL_COLS} FROM Topics tp JOIN Materials m ON m.TopicId = tp.Id
    {MATERIAL_JOINS} WHERE tp.SyllabusId = %s ORDER BY tp.OrderNo, m.OrderNo"""
SPLIT_QUESTIONS = """SELECT qq.QuizId, qq.Id, qq.OrderNo, qq.Text, qq.QType, qq.Points
    FROM Topics tp JOIN Materials m ON m.TopicId = tp.Id JOIN QuizQuestions qq ON qq.QuizId = m.Id
    WHERE tp.SyllabusId = %s ORDER BY qq.QuizId, qq.OrderNo"""
SPLIT_OPTIONS = """SELECT qo.QuestionId, qo.Id, qo.OrderNo, qo.Text, qo.IsCorrect
    FROM Topics tp JOIN Materials m ON m.TopicId = tp.Id JOIN QuizQuestions qq ON qq.QuizId = m.Id
    JOIN QuizOptions qo ON qo.QuestionId = qq.Id
    WHERE tp.SyllabusId = %s ORDER BY qo.QuestionId, qo.OrderNo"""
SPLIT_RUBRIC = """SELECT r.AssignmentId, r.Id, r.OrderNo, r.Criterion, r.Points
    FROM Topics tp JOIN Materials m ON m.TopicId = tp.Id JOIN AssignmentRubric r ON r.AssignmentId = m.Id
    WHERE tp.SyllabusId = %s ORDER BY r.AssignmentId, r.OrderNo"""


def pg_course_split(conn, sid):
    cur = conn.cursor()
    doc = dict(zip(HEADER_KEYS, cur.execute(HEADER_SQL + " WHERE s.Id = %s", (sid,)).fetchone()))
    mods = {}
    modules = []
    for tid, on, title, hours in cur.execute(SPLIT_TOPICS, (sid,)):
        mods[tid] = {"topicId": tid, "orderNo": on, "title": title, "hours": hours, "materials": []}
        modules.append(mods[tid])
    mats = {}
    for r in cur.execute(SPLIT_MATERIALS, (sid,)):
        m = _material(r[1:])
        mats[m["materialId"]] = m
        mods[r[0]]["materials"].append(m)
    qs = {}
    for quiz_id, qid, on, text, qtype, pts in cur.execute(SPLIT_QUESTIONS, (sid,)):
        q = {"questionId": qid, "orderNo": on, "text": text, "qtype": qtype, "points": pts, "options": []}
        qs[qid] = q
        mats[quiz_id]["questions"].append(q)
    # питання впорядковані за QuizId, а не OrderNo в межах курсу — порядок у списку питань тесту зберігається
    for qid, oid, on, text, ok in cur.execute(SPLIT_OPTIONS, (sid,)):
        qs[qid]["options"].append({"optionId": oid, "orderNo": on, "text": text, "isCorrect": ok})
    for aid, rid, on, crit, pts in cur.execute(SPLIT_RUBRIC, (sid,)):
        mats[aid]["rubric"].append({"criterionId": rid, "orderNo": on, "criterion": crit, "points": pts})
    doc["modules"] = modules
    return doc


# =====================================================================
# R3. Відкрити один тест (студент починає проходження)
# =====================================================================

def mongo_quiz_agg(db, qid):
    """Варіант 2: aggregation pipeline — сервер повертає лише потрібний піддокумент."""
    res = list(db.course_content.aggregate([
        {"$match": {"modules.materials.materialId": qid}},
        {"$unwind": "$modules"},
        {"$unwind": "$modules.materials"},
        {"$match": {"modules.materials.materialId": qid}},
        {"$replaceRoot": {"newRoot": "$modules.materials"}},
    ]))
    return res[0]


QUIZ_SQL = """
    SELECT m.Id, m.OrderNo, m.Title, m.IsRequired, z.TimeLimitMin, z.AttemptsAllowed, z.PassingScore,
           q.Id, q.OrderNo, q.Text, q.QType, q.Points, o.Id, o.OrderNo, o.Text, o.IsCorrect
    FROM Materials m JOIN Quizzes z ON z.MaterialId = m.Id
    JOIN QuizQuestions q ON q.QuizId = z.MaterialId
    LEFT JOIN QuizOptions o ON o.QuestionId = q.Id
    WHERE m.Id = %s ORDER BY q.OrderNo, o.OrderNo"""


def pg_quiz(conn, qid):
    cur = conn.cursor()
    rows = cur.execute(QUIZ_SQL, (qid,)).fetchall()
    r0 = rows[0]
    tags = cur.execute("SELECT array_agg(Tag ORDER BY Tag) FROM MaterialTags WHERE MaterialId = %s",
                       (qid,)).fetchone()[0] or []
    quiz = {"materialId": r0[0], "orderNo": r0[1], "type": "quiz", "title": r0[2], "isRequired": r0[3],
            "tags": tags, "timeLimitMin": r0[4], "attemptsAllowed": r0[5], "passingScore": r0[6],
            "questions": []}
    qs = {}
    for r in rows:
        q = qs.get(r[7])
        if q is None:
            q = qs[r[7]] = {"questionId": r[7], "orderNo": r[8], "text": r[9], "qtype": r[10],
                            "points": r[11], "options": []}
            quiz["questions"].append(q)
        if r[12] is not None:
            q["options"].append({"optionId": r[12], "orderNo": r[13], "text": r[14], "isCorrect": r[15]})
    return quiz


# =====================================================================
# W1. Створення курсу
# =====================================================================

def mongo_insert_course(db, doc):
    db.course_content.insert_one(doc)


def _pg_insert_tree(cur, doc):
    rows = g.doc_to_rows(doc)
    for k, (table, cols) in g.COURSE_TABLES.items():
        if rows[k]:
            cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                            rows[k])


def pg_insert_course(conn, doc):
    """Одна транзакція: метадані силабусу + 12 таблиць (executemany = пакетна вставка)."""
    with conn.transaction():
        cur = conn.cursor()
        cur.execute("UPDATE Syllabuses SET ContentVersion = %s, ContentUpdatedAt = %s WHERE Id = %s",
                    (doc["version"], doc["updatedAt"], doc["_id"]))
        _pg_insert_tree(cur, doc)


# =====================================================================
# W2. Точкова зміна: змінити бали одного питання тесту
# =====================================================================

def mongo_update_question(db, arg):
    sid, mid, qid, pts = arg
    db.course_content.update_one(
        {"_id": sid},
        {"$set": {"modules.$[].materials.$[m].questions.$[q].points": pts, "updatedAt": _now()},
         "$inc": {"version": 1}},
        array_filters=[{"m.materialId": mid}, {"q.questionId": qid}])


def pg_update_question(conn, arg):
    sid, mid, qid, pts = arg
    with conn.transaction():
        conn.execute("UPDATE QuizQuestions SET Points = %s WHERE Id = %s", (pts, qid))
        conn.execute("UPDATE Syllabuses SET ContentVersion = ContentVersion + 1, ContentUpdatedAt = %s "
                     "WHERE Id = %s", (_now(), sid))


def _now():
    dt = datetime.now(timezone.utc)
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


# =====================================================================
# W4. Запис спроби тесту (пікове навантаження під час контрольної)
# =====================================================================

def mongo_insert_attempt(db, a):
    db.quiz_attempts.insert_one(g.mongo_attempt(a))


def pg_insert_attempt(conn, a):
    rows = g.attempt_to_rows(a)
    with conn.transaction():
        cur = conn.cursor()
        for k, (table, cols) in g.ATTEMPT_TABLES.items():
            if rows[k]:
                cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES "
                                f"({', '.join(['%s'] * len(cols))})", rows[k])


# =====================================================================
# W5. Ціна денормалізації: викладач змінив ПІБ
# =====================================================================

def pg_rename_teacher(conn, arg):
    tid, name = arg
    with conn.transaction():
        conn.execute("UPDATE Users SET FullName = %s WHERE Id = (SELECT UserId FROM Teachers WHERE Id = %s)",
                     (name, tid))


def mongo_rename_teacher(db, arg):
    tid, name = arg
    db.course_content.update_many({"teacherId": tid}, {"$set": {"teacherName": name}})

# =====================================================================
# A1. Пошук матеріалів за тегом по всіх курсах
# =====================================================================

def mongo_tag_search(db, tag):
    return list(db.course_content.aggregate([
        {"$match": {"modules.materials.tags": tag}},
        {"$unwind": "$modules"},
        {"$unwind": "$modules.materials"},
        {"$match": {"modules.materials.tags": tag}},
        {"$project": {"_id": 0, "syllabusId": "$_id", "disciplineName": 1,
                      "materialId": "$modules.materials.materialId",
                      "title": "$modules.materials.title", "type": "$modules.materials.type"}},
    ]))


TAG_SQL = """
    SELECT s.Id, d.Name, m.Id, m.Title, m.Type
    FROM MaterialTags mt
    JOIN Materials m   ON m.Id = mt.MaterialId
    JOIN Topics tp     ON tp.Id = m.TopicId
    JOIN Syllabuses s  ON s.Id = tp.SyllabusId
    JOIN Disciplines d ON d.Id = s.DisciplineId
    WHERE mt.Tag = %s"""


def pg_tag_search(conn, tag):
    return [{"syllabusId": r[0], "disciplineName": r[1], "materialId": r[2], "title": r[3], "type": r[4]}
            for r in conn.execute(TAG_SQL, (tag,))]


# =====================================================================
# A2. Звіт по кафедрах: курси, тести, питання, години відео
# =====================================================================

def mongo_dept_stats(db):
    pipe = [
        {"$unwind": "$modules"},
        {"$unwind": "$modules.materials"},
        {"$group": {
            "_id": "$departmentId",
            "courses": {"$addToSet": "$_id"},
            "materials": {"$sum": 1},
            "quizzes": {"$sum": {"$cond": [{"$eq": ["$modules.materials.type", "quiz"]}, 1, 0]}},
            "questions": {"$sum": {"$size": {"$ifNull": ["$modules.materials.questions", []]}}},
            "videoSec": {"$sum": {"$ifNull": ["$modules.materials.durationSec", 0]}},
        }},
        {"$project": {"_id": 1, "courses": {"$size": "$courses"}, "materials": 1, "quizzes": 1,
                      "questions": 1, "videoSec": 1}},
        {"$sort": {"_id": 1}},
    ]
    return list(db.course_content.aggregate(pipe, allowDiskUse=True))


DEPT_SQL = """
    WITH m AS (
        SELECT t.DepartmentId AS dep, s.Id AS sid, mt.Id AS mid, mt.Type
        FROM Syllabuses s JOIN Teachers t ON t.Id = s.TeacherId
        JOIN Topics tp ON tp.SyllabusId = s.Id JOIN Materials mt ON mt.TopicId = tp.Id
        )
    SELECT m.dep, COUNT(DISTINCT m.sid), COUNT(*),
           COUNT(*) FILTER (WHERE m.Type = 'quiz'),
           COALESCE(SUM(qc.n), 0)::int, COALESCE(SUM(v.DurationSec), 0)::int
    FROM m
    LEFT JOIN MaterialVideos v ON v.MaterialId = m.mid
    LEFT JOIN (SELECT QuizId, COUNT(*) n FROM QuizQuestions GROUP BY QuizId) qc ON qc.QuizId = m.mid
    GROUP BY m.dep ORDER BY m.dep"""

def pg_dept_stats(conn):
    rows = conn.execute(DEPT_SQL).fetchall()
    return [{"_id": r[0], "courses": r[1], "materials": r[2], "quizzes": r[3], "questions": r[4],
             "videoSec": r[5]} for r in rows]
