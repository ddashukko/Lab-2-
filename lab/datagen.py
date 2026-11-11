"""Генератор тестових даних (seed фіксований — дані завжди однакові).

Кожен курс генерується один раз як Python-словник і записується в обидві БД:
у MongoDB — як документ, у PostgreSQL — через doc_to_rows() у 12 таблиць.
Тому вміст баз однаковий, а порівнюються лише способи зберігання.
"""
import random
from datetime import datetime, timedelta, timezone

WORDS = ("дані база запит індекс таблиця документ колекція ключ значення граф вузол "
         "транзакція модель схема нормалізація реплікація шардинг кеш алгоритм структура "
         "система аналіз метод функція процедура тригер подання об'єкт клас інтерфейс "
         "мережа протокол безпека шифрування сервер клієнт архітектура тестування "
         "оптимізація продуктивність масштабування сортування пошук дерево хеш список "
         "черга стек масив рядок число вектор матриця ймовірність статистика розподіл "
         "лекція практика завдання оцінка курс модуль тема студент викладач кафедра").split()

TAGS = [f"t{i:03d}" for i in range(300)]          # словник тегів
TAG_WEIGHTS = [1.0 / (i + 1) ** 1.1 for i in range(300)]  # розподіл Ципфа: є часті й рідкісні теги

MATERIAL_TYPES = ["lecture", "video", "file", "link", "quiz", "assignment"]
MATERIAL_WEIGHTS = [25, 25, 15, 10, 15, 10]

BASE_TIME = datetime(2025, 9, 1, tzinfo=timezone.utc)


def ms(dt):
    """Обрізаємо до мілісекунд — точність BSON Date, щоб дані збігались."""
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


def text(rng, a, b):
    return " ".join(rng.choices(WORDS, k=rng.randint(a, b)))


def sentence(rng, a, b):
    s = text(rng, a, b)
    return s[0].upper() + s[1:]


class Ids:
    """Глобальні лічильники ідентифікаторів (однакові ID в обох БД)."""
    def __init__(self, start=None):
        s = start or {}
        self.topic = s.get("topic", 0)
        self.material = s.get("material", 0)
        self.question = s.get("question", 0)
        self.option = s.get("option", 0)
        self.rubric = s.get("rubric", 0)
        self.attempt = s.get("attempt", 0)
        self.answer = s.get("answer", 0)

    def next(self, name):
        v = getattr(self, name) + 1
        setattr(self, name, v)
        return v


def make_material(rng, ids, order_no):
    mtype = rng.choices(MATERIAL_TYPES, MATERIAL_WEIGHTS)[0]
    ntags = rng.choices([0, 1, 2, 3], [20, 40, 30, 10])[0]
    tags = sorted(set(rng.choices(TAGS, TAG_WEIGHTS, k=ntags)))
    m = {
        "materialId": ids.next("material"),
        "orderNo": order_no,
        "type": mtype,
        "title": sentence(rng, 2, 6),
        "isRequired": rng.random() < 0.8,
        "tags": tags,
    }
    if mtype == "lecture":
        m["body"] = sentence(rng, 60, 250)
        m["readingTimeMin"] = rng.randint(5, 40)
    elif mtype == "video":
        m["url"] = f"https://video.lms.example/v/{m['materialId']}"
        m["durationSec"] = rng.randint(180, 5400)
    elif mtype == "file":
        m["format"] = rng.choice(["pdf", "docx", "pptx", "zip", "ipynb"])
        m["url"] = f"https://files.lms.example/f/{m['materialId']}.{m['format']}"
        m["sizeKb"] = rng.randint(20, 50000)
    elif mtype == "link":
        m["url"] = f"https://example.org/{text(rng, 1, 3).replace(' ', '-')}"
    elif mtype == "quiz":
        m["timeLimitMin"] = rng.choice([10, 15, 20, 30, 45, 60])
        m["attemptsAllowed"] = rng.randint(1, 3)
        qs = []
        for qn in range(1, rng.randint(4, 10) + 1):
            qtype = rng.choices(["single", "multiple", "text"], [65, 25, 10])[0]
            opts = []
            if qtype != "text":
                correct = {rng.randint(1, 4)} if qtype == "single" else set(rng.sample(range(1, 5), 2))
                for on in range(1, 5):
                    opts.append({"optionId": ids.next("option"), "orderNo": on,
                                 "text": sentence(rng, 1, 5), "isCorrect": on in correct})
            qs.append({"questionId": ids.next("question"), "orderNo": qn,
                       "text": sentence(rng, 6, 18) + "?", "qtype": qtype,
                       "points": rng.randint(1, 5), "options": opts})
        m["questions"] = qs
        m["passingScore"] = max(1, int(sum(q["points"] for q in qs) * 0.6))
    elif mtype == "assignment":
        m["deadline"] = ms(BASE_TIME + timedelta(days=rng.randint(0, 120), minutes=rng.randint(0, 1439)))
        rub = [{"criterionId": ids.next("rubric"), "orderNo": i,
                "criterion": sentence(rng, 3, 8), "points": rng.randint(2, 10)}
               for i in range(1, rng.randint(2, 5) + 1)]
        m["rubric"] = rub
        m["maxPoints"] = sum(r["points"] for r in rub)
    return m


def make_course(rng, ids, header, topics_range=(6, 12), materials_range=(3, 7)):
    """header: поля силабусу з реляційної частини (денормалізовані в документ)."""
    modules = []
    for tn in range(1, rng.randint(*topics_range) + 1):
        mats = [make_material(rng, ids, mn) for mn in range(1, rng.randint(*materials_range) + 1)]
        modules.append({"topicId": ids.next("topic"), "orderNo": tn,
                        "title": sentence(rng, 3, 7), "hours": rng.choice([2, 4, 6, 8]),
                        "materials": mats})
    doc = dict(header)
    doc["version"] = 1
    doc["updatedAt"] = ms(BASE_TIME + timedelta(seconds=rng.randint(0, 10_000_000)))
    doc["modules"] = modules
    return doc


def iter_quizzes(doc):
    for mod in doc["modules"]:
        for m in mod["materials"]:
            if m["type"] == "quiz":
                yield m


def make_attempt(rng, ids, doc, quiz, student_id):
    started = ms(BASE_TIME + timedelta(seconds=rng.randint(0, 10_000_000)))
    finished = ms(started + timedelta(seconds=rng.randint(120, quiz["timeLimitMin"] * 60)))
    skill = rng.random()
    answers, score, max_score = [], 0, 0
    for q in quiz["questions"]:
        max_score += q["points"]
        ok = rng.random() < 0.3 + 0.6 * skill
        if q["qtype"] == "text":
            sel, ta = [], sentence(rng, 3, 12)
        else:
            correct = [o["optionId"] for o in q["options"] if o["isCorrect"]]
            wrong = [o["optionId"] for o in q["options"] if not o["isCorrect"]]
            sel = correct if ok else [rng.choice(wrong)]
            ta = None
        pts = q["points"] if ok else 0
        score += pts
        a = {"answerId": ids.next("answer"), "questionId": q["questionId"],
             "selectedOptionIds": sel, "isCorrect": ok, "points": pts}
        if ta is not None:
            a["textAnswer"] = ta
        answers.append(a)
    return {"_id": ids.next("attempt"), "studentId": student_id, "quizId": quiz["materialId"],
            "syllabusId": doc["_id"], "quizTitle": quiz["title"],
            "startedAt": started, "finishedAt": finished,
            "score": score, "maxScore": max_score, "answers": answers}


def mongo_attempt(a):
    """answerId — технічний ключ SQL; у документі він не потрібен."""
    d = dict(a)
    d["answers"] = [{k: v for k, v in x.items() if k != "answerId"} for x in a["answers"]]
    return d


# ---------------------------------------------------------------------
# Документ -> рядки нормалізованих таблиць
# ---------------------------------------------------------------------
COURSE_TABLES = {
    "topics": ("Topics", ["Id", "SyllabusId", "Title", "Hours", "OrderNo"]),
    "materials": ("Materials", ["Id", "TopicId", "OrderNo", "Type", "Title", "IsRequired"]),
    "lectures": ("MaterialLectures", ["MaterialId", "Body", "ReadingTimeMin"]),
    "videos": ("MaterialVideos", ["MaterialId", "Url", "DurationSec"]),
    "files": ("MaterialFiles", ["MaterialId", "Url", "Format", "SizeKb"]),
    "links": ("MaterialLinks", ["MaterialId", "Url"]),
    "quizzes": ("Quizzes", ["MaterialId", "TimeLimitMin", "AttemptsAllowed", "PassingScore"]),
    "questions": ("QuizQuestions", ["Id", "QuizId", "OrderNo", "Text", "QType", "Points"]),
    "options": ("QuizOptions", ["Id", "QuestionId", "OrderNo", "Text", "IsCorrect"]),
    "assignments": ("Assignments", ["MaterialId", "Deadline", "MaxPoints"]),
    "rubric": ("AssignmentRubric", ["Id", "AssignmentId", "OrderNo", "Criterion", "Points"]),
    "tags": ("MaterialTags", ["MaterialId", "Tag"]),
}

ATTEMPT_TABLES = {
    "attempts": ("QuizAttempts", ["Id", "StudentId", "QuizId", "StartedAt", "FinishedAt", "Score", "MaxScore"]),
    "answers": ("AttemptAnswers", ["Id", "AttemptId", "QuestionId", "TextAnswer", "IsCorrect", "Points"]),
    "selections": ("AttemptAnswerSelections", ["AnswerId", "OptionId"]),
}


def doc_to_rows(doc, out=None):
    out = out if out is not None else {k: [] for k in COURSE_TABLES}
    sid = doc["_id"]
    for mod in doc["modules"]:
        out["topics"].append((mod["topicId"], sid, mod["title"], mod["hours"], mod["orderNo"]))
        for m in mod["materials"]:
            mid, t = m["materialId"], m["type"]
            out["materials"].append((mid, mod["topicId"], m["orderNo"], t, m["title"], m["isRequired"]))
            for tag in m["tags"]:
                out["tags"].append((mid, tag))
            if t == "lecture":
                out["lectures"].append((mid, m["body"], m["readingTimeMin"]))
            elif t == "video":
                out["videos"].append((mid, m["url"], m["durationSec"]))
            elif t == "file":
                out["files"].append((mid, m["url"], m["format"], m["sizeKb"]))
            elif t == "link":
                out["links"].append((mid, m["url"]))
            elif t == "quiz":
                out["quizzes"].append((mid, m["timeLimitMin"], m["attemptsAllowed"], m["passingScore"]))
                for q in m["questions"]:
                    out["questions"].append((q["questionId"], mid, q["orderNo"], q["text"], q["qtype"], q["points"]))
                    for o in q["options"]:
                        out["options"].append((o["optionId"], q["questionId"], o["orderNo"], o["text"], o["isCorrect"]))
            elif t == "assignment":
                out["assignments"].append((mid, m["deadline"], m["maxPoints"]))
                for r in m["rubric"]:
                    out["rubric"].append((r["criterionId"], mid, r["orderNo"], r["criterion"], r["points"]))
    return out


def attempt_to_rows(a, out=None):
    out = out if out is not None else {k: [] for k in ATTEMPT_TABLES}
    out["attempts"].append((a["_id"], a["studentId"], a["quizId"], a["startedAt"], a["finishedAt"],
                            a["score"], a["maxScore"]))
    for x in a["answers"]:
        out["answers"].append((x["answerId"], a["_id"], x["questionId"], x.get("textAnswer"),
                               x["isCorrect"], x["points"]))
        for oid in x["selectedOptionIds"]:
            out["selections"].append((x["answerId"], oid))
    return out
