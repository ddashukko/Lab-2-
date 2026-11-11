-- =====================================================================
-- Базова схема «Система управління навчальними курсами» (з попередньої лаби)
-- Відтворено з ER-діаграми звіту. Єдина зміна: у Users додано FullName,
-- бо в контенті курсу потрібно показувати ПІБ викладача.
-- =====================================================================
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

CREATE TABLE Users (
    Id            SERIAL PRIMARY KEY,
    Email         VARCHAR(255) NOT NULL UNIQUE,
    FullName      VARCHAR(200) NOT NULL,
    PasswordHash  VARCHAR(255) NOT NULL,
    Role          VARCHAR(20)  NOT NULL CHECK (Role IN ('Admin','Teacher','Student')),
    IsDeleted     BOOLEAN      NOT NULL DEFAULT FALSE,
    UpdatedAt     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UpdatedById   INT REFERENCES Users(Id)
);

CREATE TABLE Departments (
    Id        SERIAL PRIMARY KEY,
    Name      VARCHAR(200) NOT NULL,
    ShortName VARCHAR(20)  NOT NULL
);

CREATE TABLE Teachers (
    Id           SERIAL PRIMARY KEY,
    UserId       INT NOT NULL UNIQUE REFERENCES Users(Id),
    DepartmentId INT NOT NULL REFERENCES Departments(Id),
    Position     VARCHAR(100),
    Degree       VARCHAR(100)
);

CREATE TABLE AcademicGroups (
    Id           SERIAL PRIMARY KEY,
    Name         VARCHAR(20) NOT NULL UNIQUE,
    EntryYear    INT NOT NULL,
    DepartmentId INT NOT NULL REFERENCES Departments(Id)
);

CREATE TABLE Students (
    Id               SERIAL PRIMARY KEY,
    UserId           INT NOT NULL UNIQUE REFERENCES Users(Id),
    GroupId          INT NOT NULL REFERENCES AcademicGroups(Id),
    RecordBookNumber VARCHAR(20) NOT NULL UNIQUE,
    StudyForm        VARCHAR(20) NOT NULL DEFAULT 'Budget'
);

CREATE TABLE Disciplines (
    Id          SERIAL PRIMARY KEY,
    Name        VARCHAR(200) NOT NULL,
    Code        VARCHAR(20)  NOT NULL UNIQUE,
    IsDeleted   BOOLEAN      NOT NULL DEFAULT FALSE,
    UpdatedAt   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UpdatedById INT REFERENCES Users(Id)
);

CREATE TABLE Semesters (
    Id           SERIAL PRIMARY KEY,
    AcademicYear VARCHAR(9) NOT NULL,      -- '2024/2025'
    Number       INT NOT NULL CHECK (Number IN (1,2)),
    UNIQUE (AcademicYear, Number)
);

CREATE TABLE Curriculums (
    Id           SERIAL PRIMARY KEY,
    GroupId      INT NOT NULL REFERENCES AcademicGroups(Id),
    DisciplineId INT NOT NULL REFERENCES Disciplines(Id),
    SemesterId   INT NOT NULL REFERENCES Semesters(Id),
    TotalHours   INT NOT NULL,
    UNIQUE (GroupId, DisciplineId, SemesterId)
);

CREATE TABLE Syllabuses (
    Id           SERIAL PRIMARY KEY,
    DisciplineId INT NOT NULL REFERENCES Disciplines(Id),
    TeacherId    INT NOT NULL REFERENCES Teachers(Id),
    SemesterId   INT NOT NULL REFERENCES Semesters(Id),
    Description  TEXT
);

-- Topics у новій версії переїжджають у документ MongoDB (модулі курсу).
-- У SQL-варіанті вони залишаються таблицею, розширеною полем OrderNo
-- (див. 02_course_content.sql).
CREATE TABLE Topics (
    Id          SERIAL PRIMARY KEY,
    SyllabusId  INT NOT NULL REFERENCES Syllabuses(Id) ON DELETE CASCADE,
    Title       VARCHAR(300) NOT NULL,
    Hours       INT NOT NULL,
    IsDeleted   BOOLEAN NOT NULL DEFAULT FALSE,
    UpdatedAt   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UpdatedById INT REFERENCES Users(Id)
);

CREATE TABLE ClassTypes (
    Id   SERIAL PRIMARY KEY,
    Name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE Classrooms (
    Id         SERIAL PRIMARY KEY,
    Building   VARCHAR(50) NOT NULL,
    RoomNumber VARCHAR(20) NOT NULL,
    Capacity   INT NOT NULL
);

CREATE TABLE Schedule (
    Id           SERIAL PRIMARY KEY,
    CurriculumId INT NOT NULL REFERENCES Curriculums(Id),
    TeacherId    INT NOT NULL REFERENCES Teachers(Id),
    ClassroomId  INT NOT NULL REFERENCES Classrooms(Id),
    ClassTypeId  INT NOT NULL REFERENCES ClassTypes(Id),
    LessonDate   DATE NOT NULL,
    StartTime    TIME NOT NULL,
    EndTime      TIME NOT NULL,
    UpdatedAt    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UpdatedById  INT REFERENCES Users(Id),
    UNIQUE (ClassroomId, LessonDate, StartTime)
);

CREATE TABLE Attendance (
    Id         SERIAL PRIMARY KEY,
    ScheduleId INT NOT NULL REFERENCES Schedule(Id),
    StudentId  INT NOT NULL REFERENCES Students(Id),
    IsPresent  BOOLEAN NOT NULL,
    Points     NUMERIC(5,2)
);

CREATE TABLE ExamRecords (
    Id           SERIAL PRIMARY KEY,
    CurriculumId INT NOT NULL REFERENCES Curriculums(Id),
    StudentId    INT NOT NULL REFERENCES Students(Id),
    Grade        NUMERIC(5,2),
    DatePassed   DATE,
    IsDeleted    BOOLEAN NOT NULL DEFAULT FALSE,
    UpdatedAt    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UpdatedById  INT REFERENCES Users(Id)
);

-- Індекси з попередньої лаби
CREATE INDEX idx_schedule_lessondate   ON Schedule(LessonDate);
CREATE INDEX idx_examrecords_studentid ON ExamRecords(StudentId);
CREATE INDEX idx_examrecords_active    ON ExamRecords(StudentId) WHERE IsDeleted = FALSE;
CREATE INDEX idx_disciplines_active    ON Disciplines(Code)      WHERE IsDeleted = FALSE;

-- Індекси на FK, потрібні для сценаріїв цієї лаби
CREATE INDEX idx_syllabuses_teacher  ON Syllabuses(TeacherId);
CREATE INDEX idx_syllabuses_semester ON Syllabuses(SemesterId);
CREATE INDEX idx_teachers_department ON Teachers(DepartmentId);
CREATE INDEX idx_topics_syllabus     ON Topics(SyllabusId);
