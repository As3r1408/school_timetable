from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student' or 'staff'

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.Date, nullable=False)  # Stores the full date (YYYY-MM-DD)
    week = db.Column(db.Integer, nullable=False)  # Stores the week number
    day_of_week = db.Column(db.String(10), nullable=False)  # "Monday", "Tuesday", etc.
    subject = db.Column(db.String(100), nullable=False)
    teacher = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.Time, nullable=False)  # HH:MM format
    end_time = db.Column(db.Time, nullable=False)  # HH:MM format

    user = db.relationship('User', backref='timetables')

    def __init__(self, user_id, date, subject, teacher, start_time, end_time):
        self.user_id = user_id
        self.date = date
        self.subject = subject
        self.teacher = teacher
        self.start_time = start_time
        self.end_time = end_time
        self.week = date.isocalendar()[1]  # Auto-calculate week number
        self.day_of_week = date.strftime('%A')  # Convert date to day name
