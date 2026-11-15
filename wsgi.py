"""Өндірістік сервер (gunicorn) үшін кіру нүктесі: gunicorn wsgi:app"""
from app import create_app
from app.database import init_db

app = create_app()
with app.app_context():
    init_db()
