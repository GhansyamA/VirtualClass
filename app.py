from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Notes, Assignment, Submission, Course, Enrollment, ActiveMeeting
from forms import LoginForm, RegisterForm, NoteUploadForm, AssignmentCreationForm, AssignmentSubmissionForm, NoteUploadForm, CourseForm
from werkzeug.utils import secure_filename
import jwt,datetime,os,random,string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
NOTES_UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'notes')
SUBMISSIONS_UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'submissions')
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx'}
os.makedirs(NOTES_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUBMISSIONS_UPLOAD_FOLDER, exist_ok=True)
app.config['NOTES_UPLOAD_FOLDER'] = NOTES_UPLOAD_FOLDER
app.config['SUBMISSIONS_UPLOAD_FOLDER'] = SUBMISSIONS_UPLOAD_FOLDER
JWT_SECRET_KEY = "your_jitsi_secret_key"

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_room_name():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(username=form.username.data, password=hashed_password, role=form.role.data)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('select_course'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/select_course', methods=['GET', 'POST'])
@login_required
def select_course():
    if current_user.role != 'teacher':
        return redirect(url_for('dashboard'))
    courses = Course.query.filter_by(teacher_id=current_user.id).all()
    if not courses:
        return redirect(url_for('create_course'))
    if request.method == 'POST':
        selected_course_id = request.form.get('course_id')
        if selected_course_id:
            session['selected_course_id'] = int(selected_course_id)
            return redirect(url_for('dashboard'))
    return render_template('select_course.html', courses=courses)

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'teacher':
        selected_course_id = session.get('selected_course_id')
        if not selected_course_id:
            return redirect(url_for('select_course'))
        current_course = Course.query.get(selected_course_id)
        if not current_course or current_course.teacher_id != current_user.id:
            return redirect(url_for('select_course'))
        return render_template('dashboard.html', current_course=current_course)
    return render_template('dashboard.html')

@app.route('/start_meeting', methods=['POST'])
@login_required
def start_meeting():
    if current_user.role != 'teacher':
        flash('Only teachers can start a meeting.', 'danger')
        return redirect(url_for('dashboard'))
    selected_course_id = session.get('selected_course_id')
    if not selected_course_id:
        flash('No course selected. Please select a course first.', 'danger')
        return redirect(url_for('select_course'))
    existing_meeting = ActiveMeeting.query.filter_by(course_id=selected_course_id).first()
    if existing_meeting:
        flash('A meeting for this course is already active.', 'danger')
        return redirect(url_for('dashboard'))
    room_name = generate_room_name()
    active_meeting = ActiveMeeting(
        room_name=room_name,
        teacher_id=current_user.id,
        course_id=selected_course_id
    )
    db.session.add(active_meeting)
    db.session.commit()
    flash('Meeting started successfully! Share the link with students.', 'success')
    jitsi_url = f"https://meet.jit.si/{active_meeting.room_name}"
    return redirect(jitsi_url)

@app.route('/join_meeting', methods=['GET'])
@login_required
def join_meeting():
    if current_user.role != 'student':
        flash('Only students can join a meeting.', 'danger')
        return redirect(url_for('dashboard'))
    selected_course_id = session.get('selected_course_id')
    if not selected_course_id:
        flash('No course selected. Please select a course first.', 'danger')
        return redirect(url_for('select_course'))
    active_meeting = ActiveMeeting.query.filter_by(course_id=selected_course_id).first()
    if not active_meeting:
        flash('No active meeting for the selected course.', 'danger')
        return redirect(url_for('dashboard'))
    jitsi_url = f"https://meet.jit.si/{active_meeting.room_name}"
    return redirect(jitsi_url)

@app.route('/stop_meeting', methods=['GET'])
@login_required
def stop_meeting():
    if current_user.role != 'teacher':
        flash('Only teachers can stop meetings.', 'danger')
        return redirect(url_for('dashboard'))
    selected_course_id = session.get('selected_course_id')
    if not selected_course_id:
        flash('No course selected. Please select a course first.', 'danger')
        return redirect(url_for('select_course'))
    active_meeting = ActiveMeeting.query.filter_by(course_id=selected_course_id).first()
    if not active_meeting:
        flash('No active meeting for the selected course.', 'danger')
        return redirect(url_for('dashboard'))
    try:
        db.session.delete(active_meeting)
        db.session.commit()
        flash('Meeting stopped successfully. You can now start a new meeting.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error stopping the meeting. Please try again later.', 'danger')
        print(f"Error: {e}")
    return redirect(url_for('dashboard'))

@app.route('/create_course', methods=['GET', 'POST'])
@login_required
def create_course():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))
    form = CourseForm()
    if form.validate_on_submit():
        course = Course(
            name=form.name.data,
            description=form.description.data,
            teacher_id=current_user.id
        )
        db.session.add(course)
        db.session.commit()
        return redirect(url_for('select_course'))
    return render_template('create_course.html', form=form)

@app.route('/view_courses')
@login_required
def view_courses():
    if current_user.role == 'teacher':
        courses = Course.query.filter_by(teacher_id=current_user.id).all()
    elif current_user.role == 'student':
        courses = Course.query.all()
    return render_template('view_courses.html', courses=courses)

@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        flash('You do not have permission to edit this course.', 'danger')
        return redirect(url_for('view_courses'))
    form = CourseForm()
    if form.validate_on_submit():
        course.name = form.name.data
        course.description = form.description.data
        db.session.commit()
        flash('Course updated successfully!', 'success')
        return redirect(url_for('view_course', course_id=course.id))
    form.name.data = course.name
    form.description.data = course.description
    return render_template('create_course.html', form=form)

@app.route('/delete_course/<int:course_id>', methods=['GET'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        flash('You do not have permission to delete this course.', 'danger')
        return redirect(url_for('view_courses'))
    try:
        db.session.delete(course)
        db.session.commit()
        flash('Course deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()  # In case of any error, rollback the transaction
        flash('Error deleting course. Please try again later.', 'danger')
        print(f"Error: {e}")
    return redirect(url_for('view_courses'))

@app.route('/view_course/<int:course_id>', methods=['GET'])
@login_required
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    enrolled_students = [enrollment.student for enrollment in course.students]
    enrolled_student_ids = [student.id for student in enrolled_students]
    return render_template(
        'view_course.html',
        course=course,
        enrolled_students=enrolled_students,
        enrolled_student_ids=enrolled_student_ids
    )

@app.route('/enroll_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def enroll_course(course_id):
    if current_user.role != 'student':
        flash('Only students can enroll in courses.', 'danger')
        return redirect(url_for('dashboard'))
    course = Course.query.get_or_404(course_id)
    existing_enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
    if existing_enrollment:
        flash('You are already enrolled in this course.', 'danger')
        return redirect(request.referrer)  # Redirect to the previous page
    enrollment = Enrollment(student_id=current_user.id, course_id=course.id)
    db.session.add(enrollment)
    db.session.commit()
    flash('You have successfully enrolled in the course!', 'success')
    return redirect(request.referrer)  # Redirect to the previous page

@app.route('/unenroll_course/<int:course_id>', methods=['GET'])
@login_required
def unenroll_course(course_id):
    if current_user.role != 'student':
        flash('Only students can unenroll from courses.', 'danger')
        return redirect(url_for('dashboard'))
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    if not enrollment:
        flash('You are not enrolled in this course.', 'danger')
        return redirect(request.referrer)  # Redirect to the previous page
    try:
        db.session.delete(enrollment)
        db.session.commit()
        flash('You have successfully unenrolled from the course.', 'success')
    except Exception as e:
        db.session.rollback()  # Rollback if any error occurs
        flash('Error unenrolling from the course. Please try again later.', 'danger')
        print(f"Error: {e}")
    return redirect(request.referrer)  # Redirect to the previous page

@app.route('/upload_notes', methods=['GET', 'POST'])
@login_required
def upload_notes():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))
    selected_course_id = session.get('selected_course_id')
    if not selected_course_id:
        return redirect(url_for('select_course'))
    form = NoteUploadForm()
    if form.validate_on_submit():
        file = form.file.data
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['NOTES_UPLOAD_FOLDER'], filename)
            file.save(file_path)
            note = Notes(
                filename=filename,
                file_path=file_path,
                uploaded_at=datetime.datetime.now(),
                teacher_id=current_user.id,
                course_id=selected_course_id
            )
            db.session.add(note)
            db.session.commit()
            return redirect(url_for('view_notes'))
    return render_template('upload_notes.html', form=form)

@app.route('/view_notes')
@login_required
def view_notes():
    selected_course_id = session.get('selected_course_id')
    if current_user.role == 'teacher' and selected_course_id:
        notes = Notes.query.filter_by(teacher_id=current_user.id, course_id=selected_course_id).all()
    else:
        notes = Notes.query.all()
    return render_template('view_notes.html', notes=notes)

@app.route('/create_assignment', methods=['GET', 'POST'])
@login_required
def create_assignment():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))
    selected_course_id = session.get('selected_course_id')
    if not selected_course_id:
        return redirect(url_for('select_course'))
    form = AssignmentCreationForm()
    if form.validate_on_submit():
        assignment = Assignment(
            title=form.title.data,
            description=form.description.data,
            due_date=form.due_date.data,
            teacher_id=current_user.id,
            course_id=selected_course_id
        )
        db.session.add(assignment)
        db.session.commit()
        return redirect(url_for('view_assignments'))
    return render_template('create_assignment.html', form=form)

@app.route('/view_assignments')
@login_required
def view_assignments():
    selected_course_id = session.get('selected_course_id')
    if current_user.role == 'teacher' and selected_course_id:
        assignments = Assignment.query.filter_by(teacher_id=current_user.id, course_id=selected_course_id).all()
    else:
        assignments = Assignment.query.all()
    return render_template('view_assignments.html', assignments=assignments)

@app.route('/submit_assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def submit_assignment(assignment_id):
    if current_user.role != 'student':
        flash('Only students can submit assignments.', 'danger')
        return redirect(url_for('dashboard'))
    assignment = Assignment.query.get_or_404(assignment_id)
    form = AssignmentSubmissionForm()
    if form.validate_on_submit():
        file = form.file.data
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['SUBMISSIONS_UPLOAD_FOLDER'], filename)
            file.save(filepath)
            submission = Submission(
                file_name=filename,
                file_path=filepath,
                student_id=current_user.id,
                assignment_id=assignment.id,
                submitted_at=datetime.datetime.now()
            )
            db.session.add(submission)
            db.session.commit()
            flash('Assignment submitted successfully!', 'success')
            return redirect(url_for('view_assignments'))
    return render_template('submit_assignment.html', form=form, assignment=assignment)

@app.route('/view_submissions/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def view_submissions(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.teacher_id != current_user.id:
        flash('You do not have permission to view these submissions.', 'danger')
        return redirect(url_for('dashboard'))
    submissions = Submission.query.filter_by(assignment_id=assignment.id).all()
    if request.method == 'POST':
        for submission in submissions:
            marks_key = f"marks_{submission.id}"
            marks = request.form.get(marks_key)
            if marks:
                submission.marks = int(marks)
        db.session.commit()
        flash('Marks updated successfully!', 'success')
        return redirect(url_for('view_submissions', assignment_id=assignment.id))
    return render_template('view_submissions.html', assignment=assignment, submissions=submissions)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
