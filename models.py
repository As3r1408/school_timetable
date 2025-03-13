from datetime import datetime, date as dt_date, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


db = SQLAlchemy()

# User Model (Admin, Staff, Students)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student', 'staff', 'admin'
    year_group = db.Column(db.String(10), nullable=True)
# School Settings Model (For Week A/B System)
class SchoolSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    use_week_ab = db.Column(db.Boolean, default=False)  # Default: No A/B week system

# Timetable Model
class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    week = db.Column(db.Integer, nullable=False)
    day_of_week = db.Column(db.String(10), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    teacher = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(100), nullable=True)

    user = db.relationship('User', backref='timetables')

    def __init__(self, user_id, date, subject, teacher, start_time, end_time, room=None,week=None):
        self.user_id = user_id
        self.subject = subject
        self.teacher = teacher
        self.start_time = start_time
        self.end_time = end_time
        self.room = room  # Room is optional
        self.week = week if week else "current"  # Default to 'current' if no week is provided

        # ✅ Ensure `date` is always a `datetime.date` object
        if isinstance(date, str):  
            self.date = datetime.strptime(date, '%Y-%m-%d').date()  
        elif isinstance(date, datetime):
            self.date = date.date()  
        elif isinstance(date, dt_date):  
            self.date = date  
        else:
            raise ValueError("Invalid date format. Expected a string, datetime, or date object.")

        # ✅ Fix: Ensure Monday entries are assigned to the correct week
        self.week = self.date.isocalendar()[1]
        if self.date.weekday() == 0:  # If it's Monday
            previous_sunday = self.date - timedelta(days=1)
            self.week = previous_sunday.isocalendar()[1] + 1

        self.day_of_week = self.date.strftime('%A')  # Convert date to day name


# Subject Model
class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

# Model to Assign Subjects to Users
class AssignedSubject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)

    user = db.relationship('User', backref='assigned_subjects')
    subject = db.relationship('Subject', backref='assigned_users')

# Room Model
class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __init__(self, name):
        self.name = name