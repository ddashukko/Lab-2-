-- =====================================================================
-- Розширення предметної області: електронний контент курсу та тести.
-- Реляційний (нормалізований) еквівалент колекцій MongoDB
--   course_content  (1 документ)  ->  Topics + Materials + 5 підтипів +
--                                     QuizQuestions + QuizOptions +
--                                     AssignmentRubric + MaterialTags
--   quiz_attempts   (1 документ)  ->  QuizAttempts + AttemptAnswers +
--                                     AttemptAnswerSelections
-- Поліморфні матеріали змодельовано «таблицею на підклас»
-- (class table inheritance): спільні поля в Materials, специфічні — в
-- окремих таблицях 1:1.
-- =====================================================================

ALTER TABLE Topics     ADD COLUMN OrderNo INT NOT NULL DEFAULT 0;
ALTER TABLE Syllabuses ADD COLUMN ContentVersion   INT NOT NULL DEFAULT 1;
ALTER TABLE Syllabuses ADD COLUMN ContentUpdatedAt TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE Materials (
    Id         SERIAL PRIMARY KEY,
    TopicId    INT NOT NULL REFERENCES Topics(Id) ON DELETE CASCADE,
    OrderNo    INT NOT NULL,
    Type       VARCHAR(20) NOT NULL
               CHECK (Type IN ('lecture','video','file','link','quiz','assignment')),
    Title      VARCHAR(300) NOT NULL,
    IsRequired BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE MaterialLectures (
    MaterialId     INT PRIMARY KEY REFERENCES Materials(Id) ON DELETE CASCADE,
    Body           TEXT NOT NULL,
    ReadingTimeMin INT  NOT NULL
);

CREATE TABLE MaterialVideos (
    MaterialId  INT PRIMARY KEY REFERENCES Materials(Id) ON DELETE CASCADE,
    Url         VARCHAR(500) NOT NULL,
    DurationSec INT NOT NULL
);

CREATE TABLE MaterialFiles (
    MaterialId INT PRIMARY KEY REFERENCES Materials(Id) ON DELETE CASCADE,
    Url        VARCHAR(500) NOT NULL,
    Format     VARCHAR(10)  NOT NULL,
    SizeKb     INT NOT NULL
);

CREATE TABLE MaterialLinks (
    MaterialId INT PRIMARY KEY REFERENCES Materials(Id) ON DELETE CASCADE,
    Url        VARCHAR(500) NOT NULL
);

CREATE TABLE Quizzes (
    MaterialId      INT PRIMARY KEY REFERENCES Materials(Id) ON DELETE CASCADE,
    TimeLimitMin    INT NOT NULL,
    AttemptsAllowed INT NOT NULL,
    PassingScore    INT NOT NULL
);

CREATE TABLE QuizQuestions (
    Id      SERIAL PRIMARY KEY,
    QuizId  INT NOT NULL REFERENCES Quizzes(MaterialId) ON DELETE CASCADE,
    OrderNo INT NOT NULL,
    Text    TEXT NOT NULL,
    QType   VARCHAR(10) NOT NULL CHECK (QType IN ('single','multiple','text')),
    Points  INT NOT NULL
);

CREATE TABLE QuizOptions (
    Id         SERIAL PRIMARY KEY,
    QuestionId INT NOT NULL REFERENCES QuizQuestions(Id) ON DELETE CASCADE,
    OrderNo    INT NOT NULL,
    Text       VARCHAR(500) NOT NULL,
    IsCorrect  BOOLEAN NOT NULL
);

CREATE TABLE Assignments (
    MaterialId INT PRIMARY KEY REFERENCES Materials(Id) ON DELETE CASCADE,
    Deadline   TIMESTAMPTZ NOT NULL,
    MaxPoints  INT NOT NULL
);

CREATE TABLE AssignmentRubric (
    Id           SERIAL PRIMARY KEY,
    AssignmentId INT NOT NULL REFERENCES Assignments(MaterialId) ON DELETE CASCADE,
    OrderNo      INT NOT NULL,
    Criterion    VARCHAR(300) NOT NULL,
    Points       INT NOT NULL
);

CREATE TABLE MaterialTags (
    MaterialId INT NOT NULL REFERENCES Materials(Id) ON DELETE CASCADE,
    Tag        VARCHAR(50) NOT NULL,
    PRIMARY KEY (MaterialId, Tag)
);

-- ---- Спроби проходження тестів --------------------------------------
CREATE TABLE QuizAttempts (
    Id         SERIAL PRIMARY KEY,
    StudentId  INT NOT NULL REFERENCES Students(Id),
    QuizId     INT NOT NULL REFERENCES Quizzes(MaterialId),
    StartedAt  TIMESTAMPTZ NOT NULL,
    FinishedAt TIMESTAMPTZ NOT NULL,
    Score      INT NOT NULL,
    MaxScore   INT NOT NULL
);

CREATE TABLE AttemptAnswers (
    Id         SERIAL PRIMARY KEY,
    AttemptId  INT NOT NULL REFERENCES QuizAttempts(Id) ON DELETE CASCADE,
    QuestionId INT NOT NULL REFERENCES QuizQuestions(Id),
    TextAnswer TEXT,
    IsCorrect  BOOLEAN NOT NULL,
    Points     INT NOT NULL
);

CREATE TABLE AttemptAnswerSelections (
    AnswerId INT NOT NULL REFERENCES AttemptAnswers(Id) ON DELETE CASCADE,
    OptionId INT NOT NULL REFERENCES QuizOptions(Id),
    PRIMARY KEY (AnswerId, OptionId)
);
