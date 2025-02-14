from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from forms import LoginForm, RegisterForm, NoteUploadForm, AssignmentCreationForm, AssignmentSubmissionForm, NoteUploadForm, CourseForm
from werkzeug.utils import secure_filename
import random,string,tempfile
from datetime import datetime

from supabase import create_client, Client
SUPABASE_URL = "https://zplmaprxfpfzmlaywyno.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpwbG1hcHJ4ZnBmem1sYXl3eW5vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzI5ODc0MTEsImV4cCI6MjA0ODU2MzQxMX0.YhLr03RloOoibQXS_ZDSL_LBHRdfDrFXK85c32AV9bk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx','png', 'jpg', 'jpeg'}
JWT_SECRET_KEY = "jitsi_secret_key"

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

@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        existing_user = supabase.table('user').select('*').eq('username', form.username.data).execute()
        if existing_user.data:
            flash('Username already taken. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
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
        enrollments = supabase.table('enrollment').select('student_id').eq('course_id', selected_course_id).execute()
        student_ids = [e['student_id'] for e in enrollments.data] if enrollments.data else []
        leaderboard = []
        if student_ids:
            students_response = supabase.table('user').select('id', 'username').in_('id', student_ids).execute()
            students = {s['id']: s['username'] for s in students_response.data} if students_response.data else {}
            assignments_response = supabase.table('assignment').select('id').eq('course_id', selected_course_id).execute()
            assignment_ids = [a['id'] for a in assignments_response.data] if assignments_response.data else []
            submissions_response = supabase.table('submission')\
                .select('student_id', 'marks', 'assignment_id')\
                .in_('assignment_id', assignment_ids).execute()
            student_marks = {student_id: 0 for student_id in student_ids}
            if submissions_response.data:
                for submission in submissions_response.data:
                    if submission['marks'] is not None:
                        student_marks[submission['student_id']] += submission['marks']
            for student_id in student_ids:
                leaderboard.append({
                    'student_id': student_id,
                    'username': students.get(student_id, 'Unknown'),
                    'total_marks': student_marks[student_id]
                })
            leaderboard.sort(key=lambda x: x['total_marks'], reverse=True)
        return render_template('dashboard.html', current_course=current_course, active_meetings=active_meetings, leaderboard=leaderboard)
    else:
        response = supabase.table('enrollment').select('course_id').eq('student_id', current_user.id).execute()
        enrolled_courses_ids = [enrollment['course_id'] for enrollment in response.data] if response.data else []
        enrolled_courses = supabase.table('course').select('*').in_('id', enrolled_courses_ids).execute().data if enrolled_courses_ids else []
        response = supabase.table('active_meeting').select('*').in_('course_id', enrolled_courses_ids).execute()
        active_meetings = response.data if response else []
        leaderboard = []
        if enrolled_courses_ids:
            selected_course_id = enrolled_courses_ids[0]
            assignments_response = supabase.table('assignment').select('id').eq('course_id', selected_course_id).execute()
            assignment_ids = [a['id'] for a in assignments_response.data] if assignments_response.data else []
            submissions_response = supabase.table('submission')\
                .select('student_id', 'marks', 'assignment_id')\
                .in_('assignment_id', assignment_ids).execute()
            student_marks = {}
            if submissions_response.data:
                for submission in submissions_response.data:
                    if submission['marks'] is not None:
                        student_marks[submission['student_id']] = student_marks.get(submission['student_id'], 0) + submission['marks']
            students_response = supabase.table('user').select('id', 'username').execute()
            students = {s['id']: s['username'] for s in students_response.data} if students_response.data else {}
            for student_id in student_marks:
                leaderboard.append({
                    'student_id': student_id,
                    'username': students.get(student_id, 'Unknown'),
                    'total_marks': student_marks.get(student_id, 0)
                })
            leaderboard.sort(key=lambda x: x['total_marks'], reverse=True)
        return render_template('dashboard.html', enrolled_courses=enrolled_courses, active_meetings=active_meetings, leaderboard=leaderboard)

@app.route('/leaderboard/<int:course_id>', methods=['GET'])
@login_required
def get_leaderboard(course_id):
    if current_user.role == 'student':
        enrollments = supabase.table('enrollment').select('student_id').eq('course_id', course_id).execute()
        student_ids = [e['student_id'] for e in enrollments.data] if enrollments.data else []
        leaderboard = []
        if student_ids:
            students_response = supabase.table('user').select('id', 'username').in_('id', student_ids).execute()
            students = {s['id']: s['username'] for s in students_response.data} if students_response.data else {}
            assignments_response = supabase.table('assignment').select('id').eq('course_id', course_id).execute()
            assignment_ids = [a['id'] for a in assignments_response.data] if assignments_response.data else []
            submissions_response = supabase.table('submission')\
                .select('student_id', 'marks', 'assignment_id')\
                .in_('assignment_id', assignment_ids).execute()
            student_marks = {student_id: 0 for student_id in student_ids}
            if submissions_response.data:
                for submission in submissions_response.data:
                    if submission['marks'] is not None:
                        student_marks[submission['student_id']] += submission['marks']
            for student_id in student_ids:
                leaderboard.append({
                    'student_id': student_id,
                    'username': students.get(student_id, 'Unknown'),
                    'total_marks': student_marks[student_id]
                })
            leaderboard.sort(key=lambda x: x['total_marks'], reverse=True)
        return jsonify({'students': leaderboard})
    return jsonify({'error': 'Unauthorized'}), 403

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
        flash('Meeting started successfully!', 'success')
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
            flash('Meeting ended.', 'success')
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

    try:
        # Fetch enrolled courses
        enrolled_response = supabase.table('enrollment').select('course_id')\
            .eq('student_id', current_user.id).execute()
        enrolled_courses = [enrollment['course_id'] for enrollment in enrolled_response.data]

        # Fetch pending requests
        pending_response = supabase.table('enrollment_request').select('course_id')\
            .eq('student_id', current_user.id).execute()
        pending_requests = [req['course_id'] for req in pending_response.data]

        # Fetch all available courses
        query = supabase.table('course').select('*')
        response = query.execute()
        available_courses = response.data if response else []

        # Pass data to template
        return render_template('available_courses.html',
                               available_courses=available_courses,
                               enrolled_courses=enrolled_courses,
                               pending_requests=pending_requests)
    except Exception as e:
        flash(f"Error loading courses: {str(e)}", "danger")
        return redirect(url_for('dashboard'))

@app.route('/view_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def view_course(course_id):
    # Fetch course details
    course_response = supabase.table('course').select('*').eq('id', course_id).execute()
    if not course_response or not course_response.data:
        flash("Course not found.", "danger")
        return redirect(url_for('view_courses'))
    course = course_response.data[0]
    # Fetch enrollment requests
    requests_response = supabase.table('enrollment_request').select('*').eq('course_id', course_id).execute()
    enrollment_requests = []
    if requests_response and requests_response.data:
        student_ids = [req['student_id'] for req in requests_response.data]
        students_response = supabase.table('user').select('*').in_('id', student_ids).execute()
        student_data = {s['id']: s for s in students_response.data}
        enrollment_requests = [{'id': req['id'], 'student': student_data[req['student_id']]} for req in requests_response.data]
    # Fetch enrolled students
    enrolled_response = supabase.table('enrollment').select('student_id')\
        .eq('course_id', course_id).execute()
    enrolled_students = []
    if enrolled_response and enrolled_response.data:
        student_ids = [enrollment['student_id'] for enrollment in enrolled_response.data]
        students_response = supabase.table('user').select('*').in_('id', student_ids).execute()
        enrolled_students = students_response.data if students_response.data else []

    return render_template('view_course.html',
                           course=course,
                           enrollment_requests=enrollment_requests,
                           enrolled_students=enrolled_students)

@app.route('/request_enrollment/<int:course_id>', methods=['POST'])
@login_required
def request_enrollment(course_id):
    if current_user.role != 'student':
        return jsonify({"success": False, "message": "Only students can request enrollment."}), 403
    try:
        # Check if already enrolled
        enrolled_response = supabase.table('enrollment').select('*')\
            .eq('student_id', current_user.id).eq('course_id', course_id).execute()
        if enrolled_response.data:
            return jsonify({"success": False, "message": "Already enrolled."}), 400

        # Check if a request is already pending
        pending_response = supabase.table('enrollment_request').select('*')\
            .eq('student_id', current_user.id).eq('course_id', course_id).execute()
        if pending_response.data:
            return jsonify({"success": False, "message": "Request already pending."}), 400

        # Insert new request
        request_data = {
            'student_id': current_user.id,
            'course_id': course_id
        }
        supabase.table('enrollment_request').insert([request_data]).execute()
        return jsonify({"success": True, "message": "Enrollment request sent."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/process_request/<int:request_id>/<action>', methods=['POST'])
@login_required
def process_request(request_id, action):
    if current_user.role != 'teacher':
        return jsonify({"success": False, "message": "Unauthorized action"}), 403
    try:
        # Fetch the request
        request_response = supabase.table('enrollment_request').select('*').eq('id', request_id).execute()
        if not request_response or not request_response.data:
            return jsonify({"success": False, "message": "Request not found"}), 404
        enrollment_request = request_response.data[0]

        if action == 'approve':
            # Approve request and add to enrollment
            enrollment = {
                'student_id': enrollment_request['student_id'],
                'course_id': enrollment_request['course_id']
            }
            supabase.table('enrollment').insert([enrollment]).execute()
            supabase.table('enrollment_request').delete().eq('id', request_id).execute()
            return jsonify({"success": True, "message": "Request approved"})
        elif action == 'reject':
            # Reject request
            supabase.table('enrollment_request').delete().eq('id', request_id).execute()
            return jsonify({"success": True, "message": "Request rejected"})
        else:
            return jsonify({"success": False, "message": "Invalid action"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/unenroll/<int:course_id>', methods=['POST']) 
@login_required
def unenroll(course_id):
    if current_user.role != 'student':
        flash('Only students can unenroll from courses.', 'danger')
        return redirect(url_for('dashboard'))    
    response = supabase.table('enrollment').select('*').eq('student_id', current_user.id).eq('course_id', course_id).execute()
    if response and response.data:
        enrollment = response.data[0]
        assignments_response = supabase.table('assignment').select('*').eq('course_id', course_id).execute()
        if assignments_response and assignments_response.data:
            for assignment in assignments_response.data:
                submission_response = supabase.table('submission') \
                    .select('*') \
                    .eq('student_id', current_user.id) \
                    .eq('assignment_id', assignment['id']) \
                    .execute()
                if submission_response and submission_response.data:
                    submission = submission_response.data[0]
                    delete_submission_response = supabase.table('submission').delete().eq('id', submission['id']).execute()
                    if delete_submission_response:
                        file_path = f"VirtualClassBucket/submissions/{submission['file_name']}"
                        storage = supabase.storage
                        storage.from_("VirtualClassBucket").remove([file_path])

                        flash('Your submission has been removed successfully.', 'success')
                    else:
                        flash('Error removing your submission from the database.', 'danger')
                else:
                    flash('No submission found for this assignment.', 'warning')
        else:
            flash('No assignments found for this course.', 'warning')
        delete_enrollment_response = supabase.table('enrollment').delete().eq('id', enrollment['id']).execute()
        if delete_enrollment_response:
            flash('You have successfully unenrolled from the course.', 'success')
        else:
            flash('Error unenrolling from the course. Please try again later.', 'danger')
    else:
        flash('You are not enrolled in this course.', 'danger')
    return redirect(url_for('dashboard'))

def upload_to_supabase_storage(file, filename, folder):
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        file.save(tmp_file.name)
        file_path = f"VirtualClassBucket/{folder}/{filename}"
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
            file_url = upload_to_supabase_storage(file, filename, "notes")
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

@app.route('/delete_note/<int:note_id>', methods=['POST'])
@login_required
def delete_note(note_id):
    if current_user.role != 'teacher':
        flash('Only teachers can delete notes.', 'danger')
        return redirect(url_for('view_notes'))
    note_response = supabase.table('notes').select('*').eq('id', note_id).execute()
    note = note_response.data[0] if note_response and note_response.data else None
    if not note:
        flash('Note not found.', 'danger')
        return redirect(url_for('view_notes'))
    file_path = f"VirtualClassBucket/notes/{note['filename']}"
    storage = supabase.storage
    storage.from_("VirtualClassBucket").remove([file_path])
    response = supabase.table('notes').delete().eq('id', note_id).execute()
    if response:
        flash('Note and its file deleted successfully.', 'success')
    else:
        flash(f"Error deleting note: {response.json()}", 'danger')
    return redirect(url_for('view_notes'))

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
        try:
            due_date = form.due_date.data
            due_date_str = due_date.strftime('%Y-%m-%dT%H:%M:%S') if due_date else None
            assignment_data = {
                'title': form.title.data,
                'description': form.description.data,
                'due_date': due_date_str,
                'teacher_id': current_user.id,
                'course_id': selected_course_id
            }
            response = supabase.table('assignment').insert([assignment_data]).execute()
            if response.data:
                flash('Assignment created successfully!', 'success')
                return redirect(url_for('view_assignments'))
            else:
                flash(f"Error inserting assignment: {response.error_message}", 'danger')
        except Exception as e:
            flash(f"An error occurred while creating the assignment: {str(e)}", 'danger')
    formatted_due_date = form.due_date.data.strftime('%Y-%m-%dT%H:%M') if form.due_date.data else None
    return render_template('create_assignment.html', form=form, formatted_due_date=formatted_due_date)

@app.route('/delete_assignment/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != 'teacher':
        flash('Only teachers can delete assignments.', 'danger')
        return redirect(url_for('view_assignments'))
    assignment_response = supabase.table('assignment').select('*').eq('id', assignment_id).execute()
    assignment = assignment_response.data[0] if assignment_response and assignment_response.data else None
    if not assignment:
        flash('Assignment not found.', 'danger')
        return redirect(url_for('view_assignments'))
    submission_response = supabase.table('submission').delete().eq('assignment_id', assignment_id).execute()
    delete_response = supabase.table('assignment').delete().eq('id', assignment_id).execute()
    if delete_response:
        flash('Assignment and its related submissions have been deleted successfully.', 'success')
    else:
        flash('Error deleting assignment.', 'danger')
    return redirect(url_for('view_assignments'))

@app.route('/view_assignments')
@login_required
def view_assignments():
    flag = 1
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
            flag = 0
    assignments = response.data
    if current_user.role == 'student':
        submissions = supabase.table('submission').select('*').eq('student_id', current_user.id).execute()
        submission_map = {submission['assignment_id']: submission for submission in submissions.data}
    for assignment in assignments:
        due_date = assignment.get('due_date')
        if due_date:
            try:
                parsed_date = datetime.fromisoformat(due_date)
                assignment['formatted_due_date'] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                print(f"Error parsing date: {due_date}")
                assignment['formatted_due_date'] = "Invalid date"
        if current_user.role == 'student' and assignment['id'] in submission_map:
            assignment['is_submitted'] = True
        else:
            assignment['is_submitted'] = False
    return render_template('view_assignments.html', assignments=assignments, flag=flag)

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
            try:
                filename = secure_filename(file.filename)
                file_url = upload_to_supabase_storage(file, filename, "submissions")
                submission_data = {
                    'file_name': filename,
                    'file_url': file_url,
                    'student_id': current_user.id,
                    'assignment_id': assignment_id,
                    'submitted_at': datetime.now().isoformat()
                }
                response = supabase.table('submission').insert([submission_data]).execute()
                if response and response.data:
                    flash('Assignment submitted successfully!', 'success')
                    return redirect(url_for('view_assignments'))
                else:
                    flash(f"Error submitting assignment: {response.json()}", 'danger')
            except Exception as e:
                flash(f"An error occurred while uploading the file: {str(e)}", 'danger')
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
    student_ids = {submission['student_id'] for submission in submissions}
    student_response = supabase.table('user').select('*').in_('id', list(student_ids)).execute()
    if student_response and student_response.data:
        students = {student['id']: student for student in student_response.data}
    else:
        students = {}
    for submission in submissions:
        student = students.get(submission['student_id'])
        if student:
            submission['student'] = student
        if submission.get('submitted_at'):
            submission['submitted_at'] = datetime.fromisoformat(submission['submitted_at']).strftime('%Y-%m-%d %H:%M:%S')
    if request.method == 'POST':
        for submission in submissions:
            marks_key = f"marks_{submission['id']}"
            marks = request.form.get(marks_key)
            if marks and marks.isdigit():
                response = supabase.table('submission').update({'marks': int(marks)}).eq('id', submission['id']).execute()
                if response:
                    flash('Marks updated successfully!', 'success')
                else:
                    flash(f"Error updating marks: {response.json()}", 'danger')
    return render_template('view_submissions.html', assignment=assignment, submissions=submissions)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
