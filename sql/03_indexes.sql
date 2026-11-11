-- Індекси створюються ПІСЛЯ масового завантаження (так швидше і так само
-- зроблено для MongoDB). Кожному індексу MongoDB відповідає еквівалент тут.
CREATE INDEX idx_topics_syllabus_order ON Topics(SyllabusId, OrderNo);
CREATE INDEX idx_materials_topic       ON Materials(TopicId, OrderNo);
CREATE INDEX idx_questions_quiz        ON QuizQuestions(QuizId, OrderNo);
CREATE INDEX idx_options_question      ON QuizOptions(QuestionId, OrderNo);
CREATE INDEX idx_rubric_assignment     ON AssignmentRubric(AssignmentId, OrderNo);
CREATE INDEX idx_materialtags_tag      ON MaterialTags(Tag);           -- ~ {"modules.materials.tags":1}

CREATE INDEX idx_attempts_student      ON QuizAttempts(StudentId, FinishedAt DESC); -- ~ {studentId:1, finishedAt:-1}
CREATE INDEX idx_attempts_quiz         ON QuizAttempts(QuizId);                     -- ~ {quizId:1}
CREATE INDEX idx_answers_attempt       ON AttemptAnswers(AttemptId);
CREATE INDEX idx_answers_question      ON AttemptAnswers(QuestionId);
-- Без цього індексу каскадне видалення QuizOptions (заміна курсу) сканує всю таблицю
-- відповідей для КОЖНОГО варіанту: заміна курсу тривала ~1.6 с замість ~10 мс.
CREATE INDEX idx_selections_option     ON AttemptAnswerSelections(OptionId);

ANALYZE;
