// mongosh "mongodb://localhost:27017/lms" mongo/setup.js
// Створення колекцій з валідацією схеми ($jsonSchema) та індексів.
db = db.getSiblingDB("lms");
db.course_content.drop();
db.quiz_attempts.drop();

// ---------------------------------------------------------------------
// course_content: 1 документ = увесь електронний курс одного силабусу.
// _id = Syllabuses.Id (зв'язок з реляційною частиною системи).
// ---------------------------------------------------------------------
const material = {
  bsonType: "object",
  required: ["materialId", "orderNo", "type", "title", "isRequired", "tags"],
  properties: {
    materialId: { bsonType: "int" },
    orderNo:    { bsonType: "int" },
    type:       { enum: ["lecture", "video", "file", "link", "quiz", "assignment"] },
    title:      { bsonType: "string", maxLength: 300 },
    isRequired: { bsonType: "bool" },
    tags:       { bsonType: "array", items: { bsonType: "string" } },
    // поля підтипів (присутні лише у відповідного type)
    body: { bsonType: "string" }, readingTimeMin: { bsonType: "int" },
    url:  { bsonType: "string" }, durationSec: { bsonType: "int" },
    format: { bsonType: "string" }, sizeKb: { bsonType: "int" },
    timeLimitMin: { bsonType: "int" }, attemptsAllowed: { bsonType: "int" },
    passingScore: { bsonType: "int" },
    questions: {
      bsonType: "array",
      items: {
        bsonType: "object",
        required: ["questionId", "orderNo", "text", "qtype", "points", "options"],
        properties: {
          questionId: { bsonType: "int" },
          qtype: { enum: ["single", "multiple", "text"] },
          points: { bsonType: "int", minimum: 0 },
          options: { bsonType: "array" }
        }
      }
    },
    deadline:  { bsonType: "date" },
    maxPoints: { bsonType: "int" },
    rubric:    { bsonType: "array" }
  },
  // Поліморфізм: обов'язкові поля залежно від типу
  oneOf: [
    { properties: { type: { enum: ["lecture"] } },    required: ["body", "readingTimeMin"] },
    { properties: { type: { enum: ["video"] } },      required: ["url", "durationSec"] },
    { properties: { type: { enum: ["file"] } },       required: ["url", "format", "sizeKb"] },
    { properties: { type: { enum: ["link"] } },       required: ["url"] },
    { properties: { type: { enum: ["quiz"] } },       required: ["timeLimitMin", "attemptsAllowed", "passingScore", "questions"] },
    { properties: { type: { enum: ["assignment"] } }, required: ["deadline", "maxPoints", "rubric"] }
  ]
};

db.createCollection("course_content", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "disciplineId", "teacherId", "departmentId", "semesterId",
                 "version", "updatedAt", "modules"],
      properties: {
        _id: { bsonType: "int" },
        disciplineId: { bsonType: "int" }, disciplineCode: { bsonType: "string" },
        disciplineName: { bsonType: "string" },
        teacherId: { bsonType: "int" }, teacherName: { bsonType: "string" },
        departmentId: { bsonType: "int" }, departmentShortName: { bsonType: "string" },
        semesterId: { bsonType: "int" }, academicYear: { bsonType: "string" },
        semesterNo: { bsonType: "int" },
        version: { bsonType: "int" }, updatedAt: { bsonType: "date" },
        modules: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["topicId", "orderNo", "title", "hours", "materials"],
            properties: {
              topicId: { bsonType: "int" }, orderNo: { bsonType: "int" },
              title: { bsonType: "string" }, hours: { bsonType: "int" },
              materials: { bsonType: "array", items: material }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});


// ---------------------------------------------------------------------
// quiz_attempts: 1 документ = одна спроба тесту з усіма відповідями.
// Незмінний після запису (append-only), пишеться масово під час сесії.
// ---------------------------------------------------------------------
db.createCollection("quiz_attempts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "studentId", "quizId", "syllabusId", "quizTitle",
                 "startedAt", "finishedAt", "score", "maxScore", "answers"],
      properties: {
        _id: { bsonType: "int" }, studentId: { bsonType: "int" },
        quizId: { bsonType: "int" }, syllabusId: { bsonType: "int" },
        quizTitle: { bsonType: "string" },
        startedAt: { bsonType: "date" }, finishedAt: { bsonType: "date" },
        score: { bsonType: "int" }, maxScore: { bsonType: "int" },
        answers: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["questionId", "selectedOptionIds", "isCorrect", "points"],
            properties: {
              questionId: { bsonType: "int" },
              selectedOptionIds: { bsonType: "array", items: { bsonType: "int" } },
              textAnswer: { bsonType: "string" },
              isCorrect: { bsonType: "bool" }, points: { bsonType: "int" }
            }
          }
        }
      }
    }
  }
});

print("MongoDB: collections and indexes created");
