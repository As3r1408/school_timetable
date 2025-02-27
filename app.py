import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Timetable, SchoolSettings 

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

    # Check if Week A/B system is enabled
    school_settings = SchoolSettings.query.first()
    use_week_ab = school_settings.use_week_ab if school_settings else False

    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        subject = request.form['subject']
        teacher = request.form['teacher']
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()

        new_entry = Timetable(user_id=user_id, date=date, subject=subject, teacher=teacher,
                              start_time=start_time, end_time=end_time)
        db.session.add(new_entry)
        db.session.commit()
        flash("Timetable entry added!", "success")

    # Fetch user timetable sorted by date
    timetable_entries = Timetable.query.filter_by(user_id=user_id).order_by(Timetable.date).all()

    # Determine Week A or B
    for entry in timetable_entries:
        entry.week_type = "A" if entry.week % 2 == 0 else "B"

    return render_template('timetable.html', timetable=timetable_entries, use_week_ab=use_week_ab)


# Route for deleting timetable entries
@app.route('/delete_timetable/<int:id>', methods=['POST'])
def delete_timetable(id):
    if 'user_id' not in session:
        flash("Please log in to manage timetable entries.", "warning")
        return redirect(url_for('login'))

    entry = Timetable.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    flash("Timetable entry deleted.", "info")
    
    return redirect(url_for('timetable'))

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

    users = User.query.filter(User.role != "admin").all()  # Get all non-admin users

    if request.method == 'POST':
        user_id = request.form['user_id']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        subject = request.form['subject']
        teacher = request.form['teacher']
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()

        new_entry = Timetable(user_id=user_id, date=date, subject=subject, teacher=teacher,
                              start_time=start_time, end_time=end_time)
        db.session.add(new_entry)
        db.session.commit()
        flash("Timetable entry added!", "success")

    timetable_entries = Timetable.query.order_by(Timetable.date, Timetable.start_time).all()

    return render_template('admin_timetable.html', users=users, timetable=timetable_entries)



# Make sure this is at the BOTTOM
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        create_default_admin()
        initialize_school_settings()
        print("Database initialized successfully!")
        app.run(debug=True)
