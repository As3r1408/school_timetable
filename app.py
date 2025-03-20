import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Timetable, SchoolSettings, Room, Subject, AssignedSubject, user_timetable, Note

app = Flask(__name__)

os.makedirs("instance", exist_ok=True)

# Configure SQLite database (inside instance/)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{app.instance_path}/timetable.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')

# Initialize database
db.init_app(app)

def initialize_school_settings():
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings(use_week_ab=False)  # Default: No A/B week system
        db.session.add(settings)
        db.session.commit()

def create_default_admin():
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        hashed_password = generate_password_hash("admin123", method='pbkdf2:sha256')
        admin = User(username="admin", password=hashed_password, role="admin")
        db.session.add(admin)
        db.session.commit()
        print("Default admin account created! (Username: admin, Password: admin123)")

# Route for home page
@app.route('/')
def home():
    return render_template('home.html')

# Route for login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role  # Store role in session
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))

        flash("Invalid username or password.", "error")
        return redirect(url_for('login'))

    return render_template('login.html')

# Route for logout
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

# Route for dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("You must be logged in to access the dashboard.", "warning")
        return redirect(url_for('login'))  
    return render_template('dashboard.html', role=session['role'])

def display_timetable(user, week=None, permission_level=None):
    if not week:
        today = datetime.today()
        # Fix: Adjust the week start calculation to include Mondays
        week_start = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        week_start = week

    # Fix: Adjust week end to be inclusive
    week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
    week_range = f"{week_start.strftime('%a %d/%m')} - {week_end.strftime('%a %d/%m')}"

    # If user is staff, allow them to view other students' timetables
    if permission_level == 'staff':
        student_id = request.args.get('student_id')
        if student_id:
            selected_user = User.query.get(student_id)
            if selected_user and selected_user.role == 'student':
                user = selected_user

    # Fix: Use between for inclusive date range
    timetable_entries = Timetable.query.filter(
        Timetable.users.any(id=user.id),
        Timetable.date.between(week_start.date(), week_end.date())
    ).order_by(Timetable.date, Timetable.start_time).all()

    # Get list of students for staff members
    students = []
    if permission_level == 'staff':
        students = User.query.filter_by(role='student').all()

    return render_template(
        'timetable.html', 
        timetable=timetable_entries, 
        week_range=week_range, 
        permission_level=permission_level,
        week_start=week_start,
        timedelta=timedelta,
        students=students,
        current_user=user
    )

@app.route('/timetable', methods=['GET', 'POST'])
def timetable():
    if 'user_id' not in session:
        flash("Please log in to view your timetable.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = User.query.get(user_id)

    # Ensure week_offset exists in session
    if "week_offset" not in session:
        session["week_offset"] = 0

    # Handle week navigation
    if request.method == "POST" and "week_change" in request.form:
        session["week_offset"] += int(request.form["week_change"])

    today = datetime.today()
    # Fix: Adjust week start calculation
    week_start = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=session["week_offset"])

    return display_timetable(user, week_start, session['role'])

@app.route('/delete_timetable/<int:id>', methods=['POST'])
def delete_timetable(id):
    if 'user_id' not in session:
        flash("Please log in to manage timetable entries.", "warning")
        return redirect(url_for('login'))

    entry = Timetable.query.get_or_404(id)

    # Allow deletion if the user is an admin
    if session['role'] == "admin":
        db.session.delete(entry)
        db.session.commit()
        flash("Timetable entry deleted.", "info")
    else:
        flash("You do not have permission to delete this entry.", "danger")

    return redirect(url_for('admin_timetable'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == "create_user":
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']  # student or staff
            year_group = request.form.get('year_group') if role == 'student' else None

            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash("User already exists!", "warning")
            else:
                hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
                new_user = User(username=username, password=hashed_password, role=role, year_group=year_group)
                db.session.add(new_user)
                db.session.commit()
                flash(f"User '{username}' created successfully!", "success")

        elif action == "change_password":
            user_id = request.form['user_id']
            new_password = request.form['new_password']

            user = User.query.get(user_id)
            if user:
                user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
                db.session.commit()
                flash(f"Password changed for {user.username}!", "success")
            else:
                flash("User not found!", "danger")

        elif action == "delete_user":
            user_id = request.form['user_id']

            user = User.query.get(user_id)
            if user:
                db.session.delete(user)
                db.session.commit()
                flash(f"User '{user.username}' deleted!", "info")
            else:
                flash("User not found!", "danger")

    users = User.query.filter(User.role != "admin").all()  # Exclude admin from list
    return render_template('admin.html', users=users)

@app.route('/admin_timetable', methods=['GET', 'POST'])
def admin_timetable():
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('dashboard'))

    users = User.query.filter(User.role != "admin").all()
    staff_users = User.query.filter_by(role="staff").all()
    rooms = Room.query.all()
    subjects = Subject.query.all()
    year_groups = db.session.query(User.year_group).distinct().all()
    year_groups = [yg[0] for yg in year_groups if yg[0] is not None]
    selected_user = None
    selected_subject = None
    selected_year_group = None
    timetable_entries = []
    assigned_subjects = []
    subject_assignees = []
    year_group_users = []

    # Ensure the week_offset exists in session
    if "week_offset" not in session:
        session["week_offset"] = 0

    # Handle week navigation without losing the selected user, subject, or year group
    if request.method == "POST":
        if "week_change" in request.form:
            session["week_offset"] += int(request.form["week_change"])
        elif "user_id" in request.form:
            session["selected_user_id"] = request.form["user_id"]
            session.pop("selected_subject_id", None)  # Clear selected subject
            session.pop("selected_year_group", None)  # Clear selected year group
        elif "subject_id" in request.form:
            session["selected_subject_id"] = request.form["subject_id"]
            session.pop("selected_user_id", None)  # Clear selected user
            session.pop("selected_year_group", None)  # Clear selected year group
        elif "year_group" in request.form:
            session["selected_year_group"] = request.form["year_group"]
            session.pop("selected_user_id", None)  # Clear selected user
            session.pop("selected_subject_id", None)  # Clear selected subject

    # Ensure selected user, subject, or year group is persisted across week changes
    if "selected_user_id" in session:
        selected_user = User.query.get(session["selected_user_id"])
        if selected_user:
            assigned_subjects = AssignedSubject.query.filter_by(user_id=selected_user.id).all()
    elif "selected_subject_id" in session:
        selected_subject = Subject.query.get(session["selected_subject_id"])
        if selected_subject:
            subject_assignees = AssignedSubject.query.filter_by(subject_id=selected_subject.id).all()
    elif "selected_year_group" in session:
        selected_year_group = session["selected_year_group"]
        year_group_users = User.query.filter_by(year_group=selected_year_group).all()

    # Calculate the start and end of the selected week
    today = datetime.today()
    # Adjust the week start calculation to include Mondays
    week_start = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=session["week_offset"])
    week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
    week_range = f"{week_start.strftime('%a %d/%m')} - {week_end.strftime('%a %d/%m')}"

    # Modify the timetable queries to use inclusive datetime comparison
    if selected_user:
        timetable_entries = Timetable.query.filter(
            Timetable.users.any(id=selected_user.id),
            Timetable.date.between(week_start.date(), week_end.date())
        ).order_by(Timetable.date, Timetable.start_time).all()
    elif selected_subject:
        assignee_ids = [assignment.user_id for assignment in subject_assignees]
        timetable_entries = Timetable.query.filter(
            Timetable.users.any(User.id.in_(assignee_ids)),
            Timetable.date.between(week_start.date(), week_end.date())
        ).order_by(Timetable.date, Timetable.start_time).all()
    elif selected_year_group:
        year_group_user_ids = [user.id for user in year_group_users]
        timetable_entries = Timetable.query.filter(
            Timetable.users.any(User.id.in_(year_group_user_ids)),
            Timetable.date.between(week_start.date(), week_end.date())
        ).order_by(Timetable.date, Timetable.start_time).all()

    # Handle adding a timetable entry
    if request.method == 'POST' and "action" in request.form:
        action = request.form["action"]

        if action == "add_entry":
            selected_user_id = request.form["user_id"]
            selected_user = User.query.get(selected_user_id)

            if selected_user:
                date = datetime.strptime(request.form["date"], '%Y-%m-%d').date()
                subject_id = request.form["subject_id"]
                teacher_id = request.form["teacher_id"]
                start_time = datetime.strptime(request.form["start_time"], '%H:%M').time()
                end_time = datetime.strptime(request.form["end_time"], '%H:%M').time()
                room_id = request.form["room_id"]

                teacher = User.query.get(teacher_id)
                subject = Subject.query.get(subject_id)
                room = Room.query.get(room_id)

                if subject and teacher and room:
                    is_substitute = 'is_substitute' in request.form
                    new_entry = Timetable(
                        date=date,
                        subject=subject.name,
                        teacher=teacher.username,
                        start_time=start_time,
                        end_time=end_time,
                        room=room.name,
                        is_substitute=is_substitute
                    )
                    new_entry.users.append(selected_user)
                    # Also add the teacher to the users list
                    new_entry.users.append(teacher)
                    db.session.add(new_entry)
                    db.session.commit()
                    flash("Timetable entry added!", "success")

                    # Redirect to prevent form resubmission on refresh
                    return redirect(url_for('admin_timetable'))

                else:
                    flash("Invalid data. Please ensure all fields are selected.", "danger")

        elif action == "delete_entry":
            entry_id = request.form["entry_id"]
            entry = Timetable.query.get(entry_id)
            if entry:
                db.session.delete(entry)
                db.session.commit()
                flash("Timetable entry deleted.", "info")

            # Redirect after deletion to prevent duplicate deletions on reload
            return redirect(url_for('admin_timetable'))

        elif action == "assign_by_subject":
            subject_id = request.form["subject_id"]
            date = datetime.strptime(request.form["date"], '%Y-%m-%d').date()
            start_time = datetime.strptime(request.form["start_time"], '%H:%M').time()
            end_time = datetime.strptime(request.form["end_time"], '%H:%M').time()
            room_id = request.form["room_id"]
            room = Room.query.get(room_id)
            subject = Subject.query.get(subject_id)

            if not subject or not room:
                flash("Invalid subject or room selection.", "danger")
                return redirect(url_for('admin_timetable'))
            
            # Get the original subject ID to find assigned users
            original_subject_id = request.form["original_subject_id"]
            
            # Retrieve users assigned to the selected subject
            assigned_users = AssignedSubject.query.filter_by(subject_id=original_subject_id).all()
            assigned_user_ids = {assignment.user_id for assignment in assigned_users}

            # Create a single timetable entry with the NEW selected subject
            teacher = User.query.get(request.form["teacher_id"])
            is_substitute = 'is_substitute' in request.form
            new_entry = Timetable(
                date=date,
                subject=subject.name,
                teacher=teacher.username,
                start_time=start_time,
                end_time=end_time,
                room=room.name,
                is_substitute=is_substitute
            )
            db.session.add(new_entry)

            # Assign timetable entry to all users assigned to the selected subject
            for user_id in assigned_user_ids:
                user = User.query.get(user_id)
                new_entry.users.append(user)

            db.session.commit()
            
            # Store the original subject ID in session to maintain context
            session["selected_subject_id"] = original_subject_id
    
            flash(f"Timetable entry added for all assigned users of '{subject.name}'!", "success")
            return redirect(url_for('admin_timetable'))
        
        elif action == "assign_by_year_group":
            year_group = request.form["year_group"]
            date = datetime.strptime(request.form["date"], '%Y-%m-%d').date()
            start_time = datetime.strptime(request.form["start_time"], '%H:%M').time()
            end_time = datetime.strptime(request.form["end_time"], '%H:%M').time()
            room_id = request.form["room_id"]
            room = Room.query.get(room_id)
            subject_id = request.form["subject_id"]
            subject = Subject.query.get(subject_id)

            if not subject or not room:
                flash("Invalid subject or room selection.", "danger")
                return redirect(url_for('admin_timetable'))

            # Retrieve users in the year group
            year_group_users = User.query.filter_by(year_group=year_group).all()
            year_group_user_ids = {user.id for user in year_group_users}

            # Create a single timetable entry
            teacher = User.query.get(request.form["teacher_id"])
            is_substitute = 'is_substitute' in request.form
            new_entry = Timetable(
                date=date,
                subject=subject.name,
                teacher=teacher.username,
                start_time=start_time,
                end_time=end_time,
                room=room.name,
                is_substitute=is_substitute
            )
            db.session.add(new_entry)

            # Assign timetable entry to all users in the year group
            for user_id in year_group_user_ids:
                user = User.query.get(user_id)
                new_entry.users.append(user)

            db.session.commit()
            flash(f"Timetable entry added for all users in year group '{year_group}'!", "success")
            return redirect(url_for('admin_timetable'))

        elif action == "delete_entry_for_user":
            entry_id = request.form["entry_id"]
            user_id = request.form["user_id"]
            entry = Timetable.query.get(entry_id)
            user = User.query.get(user_id)
            
            if entry and user:
                # If this is the last user, delete any associated note first
                if len(entry.users) <= 1:
                    if entry.note:
                        db.session.delete(entry.note)
                
                entry.users.remove(user)
                
                # If no users left, delete the entry
                if not entry.users:
                    db.session.delete(entry)
                
                db.session.commit()
                flash(f"Entry removed for user {user.username}.", "info")
            
            return redirect(url_for('admin_timetable'))

        elif action == "delete_entry_for_all":
            entry_id = request.form["entry_id"]
            entry = Timetable.query.get(entry_id)
            
            if entry:
                # First delete any associated note
                if entry.note:
                    db.session.delete(entry.note)
                    
                # Then delete the entry
                db.session.delete(entry)
                db.session.commit()
                flash("Entry deleted for all users.", "info")
            
            return redirect(url_for('admin_timetable'))

        elif action == "set_free_day":
            date = datetime.strptime(request.form["date"], '%Y-%m-%d').date()
            message = request.form["message"]
            scope = request.form["scope"]

            # Create a special timetable entry for the free day
            free_day_entry = Timetable(
                date=date,
                subject=message,  # Use subject field to store the message
                teacher="N/A",
                start_time=datetime.strptime('00:00', '%H:%M').time(),
                end_time=datetime.strptime('23:59', '%H:%M').time(),
                room="N/A",
                is_substitute=False
            )
            free_day_entry.is_free_day = True  # Add this field to your Timetable model
            db.session.add(free_day_entry)

            # Add users based on scope
            if scope == "user" and selected_user:
                free_day_entry.users.append(selected_user)
            elif scope == "subject" and selected_subject:
                for assignee in subject_assignees:
                    user = User.query.get(assignee.user_id)
                    if user:
                        free_day_entry.users.append(user)
            elif scope == "year_group" and selected_year_group:
                for user in year_group_users:
                    free_day_entry.users.append(user)
            elif scope == "all":
                all_users = User.query.filter(User.role != "admin").all()
                for user in all_users:
                    free_day_entry.users.append(user)

            db.session.commit()
            flash(f"Free day set for {date.strftime('%Y-%m-%d')}", "success")
            return redirect(url_for('admin_timetable'))

    return render_template(
        "admin_timetable.html",
        users=users, staff_users=staff_users, rooms=rooms,
        subjects=subjects, selected_user=selected_user,
        selected_subject=selected_subject, selected_year_group=selected_year_group,
        timetable=timetable_entries, assigned_subjects=assigned_subjects,
        subject_assignees=subject_assignees, year_groups=year_groups,
        year_group_users=year_group_users,
        week_range=week_range, week_start=week_start, timedelta=timedelta
    )

@app.route('/admin_subjects', methods=['GET', 'POST'])
def admin_subjects():
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('dashboard'))

    subjects = Subject.query.all()
    rooms = Room.query.all()
    users = User.query.filter(User.role.in_(["student", "staff"])).all()

    if request.method == 'POST':
        action = request.form.get("action")

        if action == "add_subject":
            subject_name = request.form["subject_name"]
            existing_subject = Subject.query.filter_by(name=subject_name).first()
            if not existing_subject:
                new_subject = Subject(name=subject_name)
                db.session.add(new_subject)
                db.session.commit()
                flash(f"Subject '{subject_name}' added!", "success")

        elif action == "delete_subject":
            subject_id = request.form["subject_id"]
            subject = Subject.query.get(subject_id)
            db.session.delete(subject)
            db.session.commit()
            flash("Subject deleted!", "info")

        elif action == "add_room":
            room_name = request.form["room_name"]
            existing_room = Room.query.filter_by(name=room_name).first()
            if not existing_room:
                new_room = Room(name=room_name)
                db.session.add(new_room)
                db.session.commit()
                flash(f"Room '{room_name}' added!", "success")

        elif action == "delete_room":
            room_id = request.form["room_id"]
            room = Room.query.get(room_id)
            db.session.delete(room)
            db.session.commit()
            flash("Room deleted!", "info")

        elif action == "assign_subject":
            user_id = request.form["user_id"]
            subject_id = request.form["subject_id"]
            existing_assignment = AssignedSubject.query.filter_by(user_id=user_id, subject_id=subject_id).first()

            if not existing_assignment:
                new_assignment = AssignedSubject(user_id=user_id, subject_id=subject_id)
                db.session.add(new_assignment)
                db.session.commit()
                flash("Subject assigned to user!", "success")

    return render_template("admin_subjects.html", subjects=subjects, rooms=rooms, users=users)

@app.route('/get_assigned_subjects/<int:user_id>')
def get_assigned_subjects(user_id):
    assigned_subjects = AssignedSubject.query.filter_by(user_id=user_id).all()
    subjects = [Subject.query.get(a.subject_id) for a in assigned_subjects]
    return jsonify([{"id": s.id, "name": s.name} for s in subjects])

@app.route('/get_assigned_users/<int:subject_id>')
def get_assigned_users(subject_id):
    assigned_users = AssignedSubject.query.filter_by(subject_id=subject_id).all()
    users = [User.query.get(a.user_id) for a in assigned_users if User.query.get(a.user_id).role == 'student']
    return jsonify([{"id": u.id, "username": u.username} for u in users])

@app.route('/get_students_by_year_group/<year_group>')
def get_students_by_year_group(year_group):
    students = User.query.filter_by(year_group=year_group, role='student').all()
    return jsonify([{"id": u.id, "username": u.username} for u in students])

@app.route('/get_entry_details/<int:entry_id>')
def get_entry_details(entry_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    entry = Timetable.query.get_or_404(entry_id)
    subject = Subject.query.filter_by(name=entry.subject).first()
    teacher = User.query.filter_by(username=entry.teacher).first()
    room = Room.query.filter_by(name=entry.room).first()

    return jsonify({
        'date': entry.date.strftime('%Y-%m-%d'),
        'start_time': entry.start_time.strftime('%H:%M'),
        'end_time': entry.end_time.strftime('%H:%M'),
        'subject_id': subject.id if subject else None,
        'teacher_id': teacher.id if teacher else None,
        'room_id': room.id if room else None
    })

@app.route('/get_entry_assignees/<int:entry_id>')
def get_entry_assignees(entry_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    entry = Timetable.query.get_or_404(entry_id)
    return jsonify([{'id': user.id, 'username': user.username} for user in entry.users])

@app.route('/update_entry_assignees', methods=['POST'])
def update_entry_assignees():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    entry_id = data.get('entry_id')
    user_ids = data.get('user_ids', [])

    entry = Timetable.query.get_or_404(entry_id)
    
    # Clear existing assignees
    entry.users = []
    
    # Add new assignees
    for user_id in user_ids:
        user = User.query.get(user_id)
        if user:
            entry.users.append(user)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/edit_entry', methods=['POST'])
def edit_entry():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        entry_id = request.form.get('entry_id')
        entry = Timetable.query.get_or_404(entry_id)

        # Update entry details
        entry.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        entry.start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        entry.end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()

        subject = Subject.query.get(request.form['subject_id'])
        teacher = User.query.get(request.form['teacher_id'])
        room = Room.query.get(request.form['room_id'])

        if not all([subject, teacher, room]):
            flash("Invalid data. Please ensure all fields are selected.", "danger")
            return redirect(url_for('admin_timetable'))

        # Update entry
        entry.subject = subject.name
        entry.teacher = teacher.username
        entry.room = room.name
        
        entry.is_substitute = 'is_substitute' in request.form
        
        # Update the teacher in the users list
        old_teacher = User.query.filter_by(username=entry.teacher).first()
        if old_teacher in entry.users:
            entry.users.remove(old_teacher)
        entry.users.append(teacher)
        
        # Update week and day_of_week
        entry.week = entry.date.isocalendar()[1]
        if entry.date.weekday() == 0:  # If it's Monday
            previous_sunday = entry.date - timedelta(days=1)
            entry.week = previous_sunday.isocalendar()[1] + 1
        entry.day_of_week = entry.date.strftime('%A')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating entry: {str(e)}", "danger")

    return redirect(url_for('admin_timetable'))

@app.route('/get_subject_users/<int:subject_id>')
def get_subject_users(subject_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    assigned_users = AssignedSubject.query.filter_by(subject_id=subject_id).all()
    users = [User.query.get(a.user_id) for a in assigned_users]
    return jsonify([{
        'id': user.id, 
        'username': user.username,
        'role': user.role,
        'year_group': user.year_group
    } for user in users if user])

@app.route('/get_subject_teachers/<int:subject_id>')
def get_subject_teachers(subject_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    is_substitute = request.args.get('is_substitute') == 'true'
    
    if is_substitute:
        # Get all staff members
        teachers = User.query.filter_by(role='staff').all()
    else:
        # Get only teachers assigned to this subject
        assigned_teachers = AssignedSubject.query.join(User).filter(
            AssignedSubject.subject_id == subject_id,
            User.role == 'staff'
        ).all()
        teachers = [User.query.get(a.user_id) for a in assigned_teachers]

    return jsonify([{
        'id': teacher.id,
        'username': teacher.username
    } for teacher in teachers if teacher])

@app.route('/add_note', methods=['POST'])
def add_note():
    if 'user_id' not in session or session['role'] not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        data = request.get_json()
        entry_id = data.get('entry_id')
        content = data.get('content')
        
        entry = Timetable.query.get_or_404(entry_id)
        
        if entry.note:
            # Update existing note
            entry.note.content = content
            entry.note.updated_at = datetime.utcnow()
        else:
            # Create new note
            note = Note(timetable_id=entry_id, content=content)
            db.session.add(note)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Note saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/get_note/<int:entry_id>')
def get_note(entry_id):
    entry = Timetable.query.get_or_404(entry_id)
    if entry.note:
        return jsonify({
            'content': entry.note.content,
            'updated_at': entry.note.updated_at.strftime('%Y-%m-%d %H:%M')
        })
    return jsonify({'error': 'No note found'}), 404

@app.route('/edit_free_day', methods=['POST'])
def edit_free_day():
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        entry_id = request.form.get('entry_id')
        entry = Timetable.query.get_or_404(entry_id)

        if not entry.is_free_day:
            flash("Invalid operation: This entry is not a free day.", "danger")
            return redirect(url_for('admin_timetable'))

        # Update free day details
        entry.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        entry.subject = request.form['message']  # Update description
        
        # Update week and day_of_week
        entry.week = entry.date.isocalendar()[1]
        if entry.date.weekday() == 0:  # If it's Monday
            previous_sunday = entry.date - timedelta(days=1)
            entry.week = previous_sunday.isocalendar()[1] + 1
        entry.day_of_week = entry.date.strftime('%A')
        
        db.session.commit()
        flash("Free day updated successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating free day: {str(e)}", "danger")

    return redirect(url_for('admin_timetable'))

# Ensure this is at the bottom
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        create_default_admin()
        initialize_school_settings()
        print("Database initialized successfully!")
    
    app.run(debug=True)

