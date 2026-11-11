// Індекси створюються після масового завантаження (як і в PostgreSQL, 03_indexes.sql)
db = db.getSiblingDB("lms");
db.course_content.createIndex({ departmentId: 1, semesterId: 1 });
db.course_content.createIndex({ teacherId: 1 });
db.course_content.createIndex({ "modules.materials.tags": 1 });        // multikey ~ idx_materialtags_tag
db.course_content.createIndex({ "modules.materials.materialId": 1 });  // пошук курсу за матеріалом
db.quiz_attempts.createIndex({ studentId: 1, finishedAt: -1 });        // ~ idx_attempts_student
db.quiz_attempts.createIndex({ quizId: 1 });                           // ~ idx_attempts_quiz
print("MongoDB: indexes created");
