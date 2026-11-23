"""Өндірістік сервер (gunicorn) үшін кіру нүктесі: gunicorn wsgi:app"""
from app import create_app

app = create_app()  # create_app() деректер қорын өзі дайындайды (init_db)
