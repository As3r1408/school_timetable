import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Timetable, SchoolSettings, Room, Subject, AssignedSubject

app = Flask(__name__)

os.makedirs("instance", exist_ok=True)

# Configure SQLite database (inside instance/)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{app.instance_path}/timetable.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')

# Initialize database
db.init_app(app)

# Create tables

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


# Route for timetable (add/view entries)
@app.route('/timetable', methods=['GET', 'POST'])
def timetable():
    if 'user_id' not in session:
        flash("Please log in to view your timetable.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Ensure week_offset exists in session
    if "week_offset" not in session:
        session["week_offset"] = 0

    # Handle week navigation
    if request.method == "POST" and "week_change" in request.form:
        session["week_offset"] += int(request.form["week_change"])

    today = datetime.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=session["week_offset"])
    week_end = week_start + timedelta(days=6)
    week_range = f"{week_start.strftime('%a %d/%m')} - {week_end.strftime('%a %d/%m')}"

    # Fetch timetable for the logged-in user and the selected week
    timetable_entries = Timetable.query.filter(
        Timetable.user_id == user_id,
        Timetable.week == week_start.isocalendar()[1]
    ).order_by(Timetable.date, Timetable.start_time).all()

    return render_template('timetable.html', timetable=timetable_entries, week_range=week_range)


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

    # Fetch school settings (Week A/B setting)
    school_settings = SchoolSettings.query.first()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == "toggle_week_ab":
            school_settings.use_week_ab = not school_settings.use_week_ab  # Toggle setting
            db.session.commit()
            flash("Week A/B setting updated!", "success")
        
        elif action == "create_user":
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']  # student or staff

            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash("User already exists!", "warning")
            else:
                hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
                new_user = User(username=username, password=hashed_password, role=role)
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
    return render_template('admin.html', users=users, use_week_ab=school_settings.use_week_ab)


@app.route('/admin_timetable', methods=['GET', 'POST'])
def admin_timetable():
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('dashboard'))

    users = User.query.filter(User.role != "admin").all()
    staff_users = User.query.filter_by(role="staff").all()
    rooms = Room.query.all()
    selected_user = None
    timetable_entries = []
    assigned_subjects = []

    # ✅ Ensure the week_offset exists in session
    if "week_offset" not in session:
        session["week_offset"] = 0

    # ✅ Handle week navigation without losing the selected user
    if request.method == "POST":
        if "week_change" in request.form:
            session["week_offset"] += int(request.form["week_change"])

        elif "user_id" in request.form:
            session["selected_user_id"] = request.form["user_id"]

    # ✅ Ensure selected user is persisted across week changes
    if "selected_user_id" in session:
        selected_user = User.query.get(session["selected_user_id"])

        if selected_user:
            # ✅ Retrieve subjects assigned to the selected user
            assigned_subjects = AssignedSubject.query.filter_by(user_id=selected_user.id).all()

    # ✅ Calculate the start and end of the selected week
    today = datetime.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=session["week_offset"])
    week_end = week_start + timedelta(days=6)
    week_range = f"{week_start.strftime('%a %d/%m')} - {week_end.strftime('%a %d/%m')}"

    # ✅ Fetch timetable for the selected user and current week
    if selected_user:
        timetable_entries = Timetable.query.filter(
            Timetable.user_id == selected_user.id,
            Timetable.week == week_start.isocalendar()[1]  # Match the correct week
        ).order_by(Timetable.date, Timetable.start_time).all()

    # ✅ Handle adding a timetable entry
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
                apply_to_all = 'apply_to_all' in request.form  # New checkbox

                teacher = User.query.get(teacher_id)
                subject = Subject.query.get(subject_id)
                room = Room.query.get(room_id)

                if subject and teacher and room:
                    # If apply_to_all is checked, add for all users assigned to the subject
                    users_to_add = [selected_user]
                    if apply_to_all:
                        # Fetch all students and staff assigned to this subject
                        users_to_add = User.query.join(AssignedSubject).filter(AssignedSubject.subject_id == subject.id).all()

                    # Add entry for all selected users
                    for user in users_to_add:
                        new_entry = Timetable(
                            user_id=user.id,
                            date=date,
                            subject=subject.name,
                            teacher=teacher.username,
                            start_time=start_time,
                            end_time=end_time,
                            room=room.name
                        )
                        db.session.add(new_entry)
                    db.session.commit()
                    flash("Timetable entry added for selected users!", "success")

                    # ✅ Redirect to prevent form resubmission on refresh
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

            # ✅ Redirect after deletion to prevent duplicate deletions on reload
            return redirect(url_for('admin_timetable'))

    return render_template(
        "admin_timetable.html",
        users=users, staff_users=staff_users, rooms=rooms,
        selected_user=selected_user, timetable=timetable_entries,
        assigned_subjects=assigned_subjects,  # ✅ Ensure assigned subjects are passed
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


# Make sure this is at the BOTTOM
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        create_default_admin()
        initialize_school_settings()
        print("Database initialized successfully!")
    
    app.run(debug=True)
