// mongosh "mongodb://localhost:27017/lms" mongo/queries.js
// Основні запити до колекцій course_content і quiz_attempts (ті самі, що в бенчмарку).
db = db.getSiblingDB("lms");
const show = (title, x) => { print("\n--- " + title); printjson(x); };

// 1. Повний курс за id силабусу (головний сценарій: сторінка курсу)
const c = db.course_content.findOne({ _id: 42 });
show("курс 42 — кількість модулів / матеріалів",
  { modules: c.modules.length, materials: c.modules.reduce((s, m) => s + m.materials.length, 0) });

// 2. Зміст курсу — проєкція лише потрібних полів
show("зміст курсу (перший модуль)", db.course_content.findOne(
  { _id: 42 },
  { disciplineName: 1, "modules.title": 1, "modules.materials.title": 1, "modules.materials.type": 1 }
).modules[0]);

// 3. Один тест за id матеріалу — aggregation pipeline з $unwind
const quizId = db.course_content.aggregate([
  { $match: { _id: 42 } }, { $unwind: "$modules" }, { $unwind: "$modules.materials" },
  { $match: { "modules.materials.type": "quiz" } }, { $limit: 1 },
  { $project: { _id: 0, id: "$modules.materials.materialId" } }]).next().id;
show("тест " + quizId, db.course_content.aggregate([
  { $match: { "modules.materials.materialId": quizId } },
  { $unwind: "$modules" }, { $unwind: "$modules.materials" },
  { $match: { "modules.materials.materialId": quizId } },
  { $replaceRoot: { newRoot: "$modules.materials" } },
  { $project: { title: 1, timeLimitMin: 1, questionsCount: { $size: "$questions" } } }]).toArray());

// 4. Оновлення вкладеного елемента: бали питання (arrayFilters)
const q = db.course_content.findOne({ _id: 42 }).modules.flatMap(m => m.materials)
  .find(m => m.type === "quiz").questions[0];
show("updateOne з arrayFilters", db.course_content.updateOne(
  { _id: 42 },
  { $set: { "modules.$[].materials.$[m].questions.$[q].points": 5, updatedAt: new Date() }, $inc: { version: 1 } },
  { arrayFilters: [{ "m.materialId": quizId }, { "q.questionId": q.questionId }] }));

// 5. Додати новий матеріал у модуль ($push)
show("$push нового матеріалу у перший модуль", db.course_content.updateOne(
  { _id: 42, "modules.orderNo": 1 },
  { $push: { "modules.$.materials": { materialId: 99999999, orderNo: 99, type: "link", title: "Додаткове читання",
                                       isRequired: false, tags: ["t001"], url: "https://example.org/read" } } }));
show("$pull — видалити його", db.course_content.updateOne(
  { _id: 42 }, { $pull: { "modules.$[].materials": { materialId: 99999999 } } }));

// 6. Валідація схеми: документ без обов'язкових полів відхиляється
try {
  db.course_content.insertOne({ _id: -1, modules: [] });
} catch (e) { show("Валідація $jsonSchema відхилила документ", e.errInfo ? e.errInfo.details.operatorName : e.message); }

// 7. Пошук за тегом по всіх курсах (multikey-індекс)
show("кількість матеріалів з тегом t020", db.course_content.aggregate([
  { $match: { "modules.materials.tags": "t020" } },
  { $unwind: "$modules" }, { $unwind: "$modules.materials" },
  { $match: { "modules.materials.tags": "t020" } }, { $count: "materials" }]).toArray());

// 8. Звіт по кафедрах за семестр
show("статистика по кафедрах (семестр 10), перші 3", db.course_content.aggregate([
  { $match: { semesterId: 10 } },
  { $unwind: "$modules" }, { $unwind: "$modules.materials" },
  { $group: { _id: "$departmentShortName", courses: { $addToSet: "$_id" }, materials: { $sum: 1 },
              videoHours: { $sum: { $divide: [{ $ifNull: ["$modules.materials.durationSec", 0] }, 3600] } } } },
  { $project: { courses: { $size: "$courses" }, materials: 1, videoHours: { $round: ["$videoHours", 1] } } },
  { $sort: { _id: 1 } }, { $limit: 3 }]).toArray());

// 9. Спроби: історія студента та аналіз питань тесту
show("3 останні спроби студента 15", db.quiz_attempts.find(
  { studentId: 15 }, { answers: 0 }).sort({ finishedAt: -1 }).limit(3).toArray());
const someQuiz = db.quiz_attempts.findOne().quizId;
show("аналіз питань тесту " + someQuiz, db.quiz_attempts.aggregate([
  { $match: { quizId: someQuiz } }, { $unwind: "$answers" },
  { $group: { _id: "$answers.questionId", n: { $sum: 1 },
              correctRate: { $avg: { $cond: ["$answers.isCorrect", 1, 0] } } } },
  { $sort: { _id: 1 } }]).toArray());

// 10. Індекси і план виконання
show("Індекси course_content", db.course_content.getIndexes().map(i => i.name));
const ex = db.course_content.find({ "modules.materials.tags": "t250" }).explain("executionStats");
show("explain: пошук за тегом t250", { stage: ex.queryPlanner.winningPlan.inputStage?.stage,
  keysExamined: ex.executionStats.totalKeysExamined, docsExamined: ex.executionStats.totalDocsExamined,
  timeMs: ex.executionStats.executionTimeMillis });
