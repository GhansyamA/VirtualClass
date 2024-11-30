-- Create User table
CREATE TABLE "user" (
    id SERIAL PRIMARY KEY,
    username VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(150) NOT NULL,
    role VARCHAR(50) NOT NULL
);

-- Create Course table
CREATE TABLE course (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    teacher_id INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES "user"(id)
);

-- Create Assignment table
CREATE TABLE assignment (
    id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    due_date TIMESTAMP NOT NULL,
    teacher_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES "user"(id),
    FOREIGN KEY (course_id) REFERENCES course(id)
);

-- Create Notes table
CREATE TABLE notes (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(150) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    teacher_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES "user"(id),
    FOREIGN KEY (course_id) REFERENCES course(id)
);

-- Create ActiveMeeting table
CREATE TABLE active_meeting (
    id SERIAL PRIMARY KEY,
    room_name VARCHAR(50) NOT NULL,
    teacher_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES "user"(id),
    FOREIGN KEY (course_id) REFERENCES course(id)
);

-- Create Submission table
CREATE TABLE submission (
    id SERIAL PRIMARY KEY,
    file_name VARCHAR(150) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    student_id INTEGER NOT NULL,
    assignment_id INTEGER NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    marks INTEGER,
    FOREIGN KEY (student_id) REFERENCES "user"(id),
    FOREIGN KEY (assignment_id) REFERENCES assignment(id)
);

-- Create Enrollment table
CREATE TABLE enrollment (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    FOREIGN KEY (student_id) REFERENCES "user"(id),
    FOREIGN KEY (course_id) REFERENCES course(id)
);
