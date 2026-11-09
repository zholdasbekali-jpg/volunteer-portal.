"""Ортақ фикстуралар: әр тест үшін жеке уақытша SQLite қоры мен PDF бумасы.
Нақты пайдаланушылардың деректері қолданылмайды — тек ойдан шығарылған тест деректері."""
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.database import get_db, transaction
from app.services import auth_service
from app.services.event_service import DATE_FMT
from config import TestConfig

PASSWORD = "Test12345"


@pytest.fixture()
def app(tmp_path):
    app = create_app(TestConfig, DATABASE=str(tmp_path / "test.db"),
                     CERTIFICATE_DIR=str(tmp_path / "certs"))
    return app


@pytest.fixture()
def ctx(app):
    """Қолданба контексі: сервистерді тікелей шақыру үшін."""
    with app.app_context():
        yield


@pytest.fixture()
def client(app):
    return app.test_client()


def when(days=5, hour=10):
    """Қатынасты күн: days>0 — болашақ, <0 — өткен."""
    d = datetime.now() + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).strftime(DATE_FMT)


class Factory:
    """Тест деректерін тікелей жасаушы (өткен іс-шараларды да қоса)."""

    def __init__(self):
        self.n = 0

    def user(self, role="volunteer", name=None, email=None):
        self.n += 1
        email = email or f"user{self.n}@example.test"
        uid = auth_service.create_user_unchecked(name or f"Тест Пайдаланушы {self.n}", email, PASSWORD, role)
        return {"id": uid, "role": role, "email": email}

    def event(self, organizer, capacity=3, days=5, status="published", title=None):
        self.n += 1
        with transaction() as db:
            return db.execute(
                "INSERT INTO events (title, description, location, event_date, capacity, organizer_id, status)"
                " VALUES (?,?,?,?,?,?,?)",
                (title or f"Іс-шара {self.n}", "Сипаттама", "Қызылорда", when(days), capacity,
                 organizer["id"], status)).lastrowid

    def registration(self, volunteer, event_id, status="pending"):
        with transaction() as db:
            return db.execute("INSERT INTO registrations (user_id, event_id, status) VALUES (?,?,?)",
                              (volunteer["id"], event_id, status)).lastrowid


@pytest.fixture()
def make(ctx):
    return Factory()


def login(client, email, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)
