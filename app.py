from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from forms import LoginForm, RegisterForm, NoteUploadForm, AssignmentCreationForm, AssignmentSubmissionForm, NoteUploadForm, CourseForm
from werkzeug.utils import secure_filename
import os,random,string,tempfile
from datetime import datetime

from supabase import create_client, Client
SUPABASE_URL = "https://zplmaprxfpfzmlaywyno.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpwbG1hcHJ4ZnBmem1sYXl3eW5vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzI5ODc0MTEsImV4cCI6MjA0ODU2MzQxMX0.YhLr03RloOoibQXS_ZDSL_LBHRdfDrFXK85c32AV9bk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx','png', 'jpg', 'jpeg'}
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
    response = supabase.table('user').select('*').eq('id', user_id).execute()
    if response.data:
        user_data = response.data[0]
        return User(id=user_data['id'], username=user_data['username'], role=user_data['role'])
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        response = supabase.table('user').insert([{
            'username': form.username.data,
            'password': hashed_password,
            'role': form.role.data
        }]).execute()
        flash('Account created successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        response = supabase.table('user').select('*').eq('username', form.username.data).execute()
        if response.data:
            user_data = response.data[0]
            if check_password_hash(user_data['password'], form.password.data):
                login_user(User(id=user_data['id'], username=user_data['username'], role=user_data['role']))
                return redirect(url_for('select_course'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/select_course', methods=['GET', 'POST'])
@login_required
def select_course():
    if current_user.role != 'teacher':
        return redirect(url_for('dashboard'))
    response = supabase.table('course').select('*').eq('teacher_id', current_user.id).execute()
    courses = []
    if response and response.data:
        courses = response.data
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
        response = supabase.table('course').select('*').eq('id', selected_course_id).execute()
        current_course = response.data[0] if response else None
        if not current_course or current_course['teacher_id'] != current_user.id:
            return redirect(url_for('select_course'))
        response = supabase.table('active_meeting').select('*').eq('teacher_id', current_user.id).execute()
        active_meetings = response.data if response else []
        return render_template('dashboard.html', current_course=current_course, active_meetings=active_meetings)
    else:
        response = supabase.table('enrollment').select('course_id').eq('student_id', current_user.id).execute()
        if response and response.data:
            enrolled_courses_ids = [enrollment['course_id'] for enrollment in response.data]
            courses_response = supabase.table('course').select('*').in_('id', enrolled_courses_ids).execute()
            enrolled_courses = courses_response.data if courses_response else []
        else:
            enrolled_courses = []
        enrolled_courses_ids = [course['id'] for course in enrolled_courses]
        response = supabase.table('active_meeting').select('*').in_('course_id', enrolled_courses_ids).execute()
        active_meetings = response.data if response else []
        return render_template('dashboard.html', enrolled_courses=enrolled_courses, active_meetings=active_meetings)

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
    response = supabase.table('active_meeting').select('*').eq('course_id', selected_course_id).execute()
    if response and response.data:
        flash('A meeting for this course is already active.', 'danger')
        return redirect(url_for('dashboard'))
    room_name = generate_room_name()
    response = supabase.table('active_meeting').insert([{
        'room_name': room_name,
        'teacher_id': current_user.id,
        'course_id': selected_course_id
    }]).execute()
    if response:
        flash('Meeting started successfully! Share the link with students.', 'success')
        jitsi_url = f"https://meet.jit.si/{room_name}"
        return render_template('start_meeting.html', jitsi_url=jitsi_url)
    flash('Error starting the meeting. Please try again later.', 'danger')
    return redirect(url_for('dashboard'))

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
    response = supabase.table('active_meeting').select('*').eq('course_id', selected_course_id).execute()
    if response and response.data:
        active_meeting = response.data[0]
        jitsi_url = f"https://meet.jit.si/{active_meeting['room_name']}"
        return redirect(jitsi_url)
    flash('No active meeting for the selected course.', 'danger')
    return redirect(url_for('dashboard'))

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
    response = supabase.table('active_meeting').select('*').eq('course_id', selected_course_id).execute()
    if response and response.data:
        active_meeting = response.data[0]
        response = supabase.table('active_meeting').delete().eq('id', active_meeting['id']).execute()
        if response:
            flash('Meeting stopped successfully. You can now start a new meeting.', 'success')
            return redirect(url_for('dashboard'))
    flash('Error stopping the meeting. Please try again later.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/create_course', methods=['GET', 'POST'])
@login_required
def create_course():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))
    form = CourseForm()
    if form.validate_on_submit():
        course_data = {
            'name': form.name.data,
            'description': form.description.data,
            'teacher_id': current_user.id
        }
        response = supabase.table('course').insert([course_data]).execute()
        if response:
            return redirect(url_for('select_course'))
        else:
            flash(f"Error: {response.json()}", 'danger')
    return render_template('create_course.html', form=form)

@app.route('/view_courses')
@login_required
def view_courses():
    if current_user.role == 'teacher':
        response = supabase.table('course').select('*').eq('teacher_id', current_user.id).execute()
    elif current_user.role == 'student':
        response = supabase.table('course').select('*').execute()
    else:
        flash('Invalid role.', 'danger')
        return redirect(url_for('dashboard'))
    if response:
        courses = response.data
        return render_template('view_courses.html', courses=courses)
    else:
        flash(f"Error fetching courses: {response.json()}", 'danger')
        return redirect(url_for('dashboard'))

@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    response = supabase.table('course').select('*').eq('id', course_id).execute()
    if response and response.data:
        course = response.data[0]
        if course['teacher_id'] != current_user.id:
            flash('You do not have permission to edit this course.', 'danger')
            return redirect(url_for('view_courses'))
        form = CourseForm()
        if form.validate_on_submit():
            updated_data = {
                'name': form.name.data,
                'description': form.description.data
            }
            update_response = supabase.table('course').update(updated_data).eq('id', course_id).execute()
            if update_response:
                flash('Course updated successfully!', 'success')
                return redirect(url_for('view_course', course_id=course_id))
            else:
                flash(f"Error updating course: {update_response.json()}", 'danger')
        form.name.data = course['name']
        form.description.data = course['description']
        return render_template('create_course.html', form=form)
    else:
        flash('Course not found.', 'danger')
        return redirect(url_for('view_courses'))

@app.route('/delete_course/<int:course_id>', methods=['GET'])
@login_required
def delete_course(course_id):
    response = supabase.table('course').select('*').eq('id', course_id).execute()
    if response and response.data:
        course = response.data[0]
        if course['teacher_id'] != current_user.id:
            flash('You do not have permission to delete this course.', 'danger')
            return redirect(url_for('view_courses'))
        try:
            delete_response = supabase.table('course').delete().eq('id', course_id).execute()
            if delete_response.status_code == 200:
                flash('Course deleted successfully!', 'success')
            else:
                flash(f"Error deleting course: {delete_response.json()}", 'danger')
        except Exception as e:
            flash('An error occurred while deleting the course. Please try again later.', 'danger')
            print(f"Error: {e}")
    else:
        flash('Course not found.', 'danger')
    return redirect(url_for('view_courses'))

@app.route('/available_courses', methods=['GET', 'POST'])
@login_required
def available_courses():
    if current_user.role != 'student':
        flash('Only students can enroll in courses.', 'danger')
        return redirect(url_for('dashboard'))
    enrolled_courses = [enrollment['course_id'] for enrollment in current_user.enrollments]
    query = supabase.table('course').select('*')
    for course_id in enrolled_courses:
        query = query.not_('id', course_id)
    response = query.execute()
    if response and response.data:
        available_courses = response.data
        if request.method == 'POST':
            course_id = request.form.get('course_id')
            if course_id:
                enrollment = {
                    'student_id': current_user.id,
                    'course_id': course_id
                }
                enroll_response = supabase.table('enrollment').insert([enrollment]).execute()
                if enroll_response:
                    flash(f'You have been enrolled in the course!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash(f"Error enrolling in the course: {enroll_response.json()}", 'danger')
        return render_template('available_courses.html', available_courses=available_courses)
    else:
        flash('No available courses to enroll in.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/view_course/<int:course_id>')
@login_required
def view_course(course_id):
    course_response = supabase.table('course').select('*').eq('id', course_id).execute()
    if course_response and course_response.data:
        course = course_response.data[0]
    else:
        flash("Course not found.", "danger")
        return redirect(url_for('view_courses'))
    enrollment_response = supabase.table('enrollment').select('student_id').eq('course_id', course_id).execute()
    if enrollment_response:
        enrolled_students = enrollment_response.data
        student_ids = [student['student_id'] for student in enrolled_students]
        student_response = supabase.table('user').select('*').in_('id', student_ids).execute()
        if student_response:
            enrolled_students_details = student_response.data
        else:
            flash("Error fetching student details.", "danger")
            enrolled_students_details = []
    else:
        flash("Error fetching enrollments.", "danger")
        enrolled_students_details = []
    return render_template('view_course.html', course=course, enrolled_students=enrolled_students_details)

@app.route('/enroll_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def enroll_course(course_id):
    if current_user.role != 'student':
        flash('Only students can enroll in courses.', 'danger')
        return redirect(url_for('dashboard'))
    response = supabase.table('enrollments').select('*').eq('student_id', current_user.id).eq('course_id', course_id).execute()
    if response.status_code == 200 and len(response.json()) > 0:
        flash('You are already enrolled in this course.', 'danger')
        return redirect(request.referrer)
    enrollment = {
        'student_id': current_user.id,
        'course_id': course_id
    }
    response = supabase.table('enrollments').insert([enrollment]).execute()
    if response.status_code == 201:
        flash('You have successfully enrolled in the course!', 'success')
    else:
        flash(f"Error: {response.json()}", 'danger')
    return redirect(request.referrer)

@app.route('/unenroll/<int:course_id>', methods=['POST'])
@login_required
def unenroll(course_id):
    if current_user.role != 'student':
        flash('Only students can unenroll from courses.', 'danger')
        return redirect(url_for('dashboard'))
    response = supabase.table('enrollment').select('*').eq('student_id', current_user.id).eq('course_id', course_id).execute()
    if response and response.data:
        enrollment = response.data[0]
        delete_response = supabase.table('enrollment').delete().eq('id', enrollment['id']).execute()
        if delete_response:
            flash('You have successfully unenrolled from the course.', 'success')
        else:
            flash('Error unenrolling from the course. Please try again later.', 'danger')
    else:
        flash('You are not enrolled in this course.', 'danger')
    return redirect(url_for('dashboard'))

def upload_to_supabase_storage(file, filename):
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        file.save(tmp_file.name)
        file_path = f"VirtualClassBucket/{filename}"
        storage = supabase.storage
        storage.from_("VirtualClassBucket").upload(file_path, tmp_file.name)
        file_url = storage.from_("VirtualClassBucket").get_public_url(file_path)
    return file_url

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
            file_url = upload_to_supabase_storage(file, filename)
            note_data = {
                'filename': filename,
                'file_url': file_url,
                'uploaded_at': datetime.now().isoformat(),
                'teacher_id': current_user.id,
                'course_id': selected_course_id
            }
            response = supabase.table('notes').insert([note_data]).execute()
            if response:
                return redirect(url_for('view_notes'))
            else:
                flash(f"Error: {response.json()}", 'danger')
    return render_template('upload_notes.html', form=form)

@app.route('/view_notes')
@login_required
def view_notes():
    if current_user.role == 'teacher':
        selected_course_id = session.get('selected_course_id')
        if not selected_course_id:
            flash('No course selected. Please select a course to view notes.', 'danger')
            return redirect(url_for('dashboard'))
        response = supabase.table('notes').select('*').eq('teacher_id', current_user.id).eq('course_id', selected_course_id).execute()
        notes = response.data
        return render_template('view_notes.html', notes=notes)
    else:
        enrolled_courses = [enrollment['course_id'] for enrollment in supabase.table('enrollment').select('*').eq('student_id', current_user.id).execute().data]
        response = supabase.table('notes').select('*').in_('course_id', enrolled_courses).execute()
        notes = response.data
        flag=1
        if not enrolled_courses:
            flag=0
        return render_template('view_notes.html', notes=notes,flag=flag)

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
        due_date_str = form.due_date.data.isoformat()
        assignment_data = {
            'title': form.title.data,
            'description': form.description.data,
            'due_date': due_date_str,
            'teacher_id': current_user.id,
            'course_id': selected_course_id
        }
        response = supabase.table('assignment').insert([assignment_data]).execute()
        if response:
            return redirect(url_for('view_assignments'))
        else:
            flash(f"Error: {response.json()}", 'danger')
    return render_template('create_assignment.html', form=form)

@app.route('/view_assignments')
@login_required
def view_assignments():
    flag=1
    if current_user.role == 'teacher':
        selected_course_id = session.get('selected_course_id')
        if not selected_course_id:
            flash('No course selected. Please select a course to view assignments.', 'danger')
            return redirect(url_for('dashboard'))
        response = supabase.table('assignment').select('*').eq('teacher_id', current_user.id).eq('course_id', selected_course_id).execute()
    else:
        enrolled_courses = [enrollment['course_id'] for enrollment in supabase.table('enrollment').select('course_id').eq('student_id', current_user.id).execute().data] 
        response = supabase.table('assignment').select('*').in_('course_id', enrolled_courses).execute()
        if not enrolled_courses:
            flag=0
    assignments = response.data
    for assignment in assignments:
        due_date = assignment.get('due_date')
        if due_date:
            try:
                parsed_date = datetime.fromisoformat(due_date)
                assignment['formatted_due_date'] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                print(f"Error parsing date: {due_date}")
                assignment['formatted_due_date'] = "Invalid date"
    return render_template('view_assignments.html', assignments=assignments,flag=flag)

@app.route('/submit_assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def submit_assignment(assignment_id):
    if current_user.role != 'student':
        flash('Only students can submit assignments.', 'danger')
        return redirect(url_for('dashboard'))
    response = supabase.table('assignment').select('*').eq('id', assignment_id).execute()
    assignment = response.data[0] if response and response.data else None
    if not assignment:
        flash('Assignment not found.', 'danger')
        return redirect(url_for('view_assignments'))
    form = AssignmentSubmissionForm()
    if form.validate_on_submit():
        file = form.file.data
        if file:
            filename = secure_filename(file.filename)
            file_url = upload_to_supabase_storage(file, filename)
            submission_data = {
                'file_name': filename,
                'file_url': file_url,
                'student_id': current_user.id,
                'assignment_id': assignment_id,
                'submitted_at': datetime.now().isoformat()
            }
            response = supabase.table('submission').insert([submission_data]).execute()
            if response:
                flash('Assignment submitted successfully!', 'success')
                return redirect(url_for('view_assignments'))
            else:
                flash(f"Error submitting assignment: {response.json()}", 'danger')
        else:
            flash('Please upload a valid file.', 'danger')
    return render_template('submit_assignment.html', form=form, assignment=assignment)

@app.route('/view_submissions/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def view_submissions(assignment_id):
    response = supabase.table('assignment').select('*').eq('id', assignment_id).execute()
    if response and response.data:
        assignment = response.data[0]
        if assignment['teacher_id'] != current_user.id:
            flash('You do not have permission to view these submissions.', 'danger')
            return redirect(url_for('dashboard'))
    else:
        flash(f"Error fetching assignment: {response.json()}", 'danger')
        return redirect(url_for('dashboard'))
    response = supabase.table('submission').select('*').eq('assignment_id', assignment_id).execute()
    if response and response.data:
        submissions = response.data
    else:
        submissions = []
        flash(f"Error fetching submissions: {response.json()}", 'danger')
    if request.method == 'POST':
        for submission in submissions:
            marks_key = f"marks_{submission['id']}"
            marks = request.form.get(marks_key)
            if marks:
                response = supabase.table('submission').update({'marks': marks}).eq('id', submission['id']).execute()
        flash('Marks updated successfully!', 'success')
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
