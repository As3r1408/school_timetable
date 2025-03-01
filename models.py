from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# User Model (Admin, Staff, Students)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student', 'staff', 'admin'

# School Settings Model (For Week A/B System)
class SchoolSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    use_week_ab = db.Column(db.Boolean, default=False)  # Default: No A/B week system

# Timetable Model
class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)  # Stores full date (YYYY-MM-DD)
    week = db.Column(db.Integer, nullable=False)  # Week number of the year
    day_of_week = db.Column(db.String(10), nullable=False)  # "Monday", "Tuesday", etc.
    subject = db.Column(db.String(100), nullable=False)
    teacher = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.Time, nullable=False)  # HH:MM format
    end_time = db.Column(db.Time, nullable=False)  # HH:MM format
    room = db.Column(db.String(100), nullable=True)  # ✅ Allow NULL values for room

    user = db.relationship('User', backref='timetables')

    def __init__(self, user_id, date, subject, teacher, start_time, end_time, room=None):
        self.user_id = user_id
        self.date = date
        self.subject = subject
        self.teacher = teacher
        self.start_time = start_time
        self.end_time = end_time
        self.room = room  # Room is optional

        # ✅ Auto-calculate week number and day of the week
        self.week = date.isocalendar()[1]  # Week number of the year
        self.day_of_week = date.strftime('%A')  # Convert date to day name


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
