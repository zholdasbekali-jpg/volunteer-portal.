"""SQLite-пен жұмыс: қосылым, схема, транзакциялар.

Барлық сұраныстар параметрленген (? орынтолтырғыштары), SQL-инъекциядан қорғау үшін.
"""
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'volunteer'
                  CHECK (role IN ('volunteer', 'organizer', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    city         TEXT NOT NULL DEFAULT '',                 -- қала (CITIES тізімінен)
    location     TEXT NOT NULL,                       -- мекенжай: көше, ғимарат, орын
    event_date   TEXT NOT NULL,                       -- 'YYYY-MM-DD HH:MM'
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    organizer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'published'
                 CHECK (status IN ('published', 'cancelled')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS registrations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    event_id      INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'attended', 'absent')),
    registered_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (user_id, event_id)
);

CREATE TABLE IF NOT EXISTS certificates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_id  INTEGER NOT NULL UNIQUE REFERENCES registrations(id) ON DELETE CASCADE,
    certificate_code TEXT NOT NULL UNIQUE,
    issued_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    pdf_path         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_date       ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_events_organizer  ON events(organizer_id);
CREATE INDEX IF NOT EXISTS idx_reg_event         ON registrations(event_id);
"""


def connect(path: str) -> sqlite3.Connection:
    """Жаңа қосылым ашады. isolation_level=None: транзакцияларды өзіміз басқарамыз."""
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # SQLite-тың LOWER() функциясы тек ASCII-мен жұмыс істейді (кирилл әріптері өзгермейді),
    # сондықтан қазақша іздеу үшін Юникодты қолдайтын функцияны тіркейміз.
    conn.create_function("PYLOWER", 1, lambda v: v.lower() if isinstance(v, str) else v,
                         deterministic=True)
    return conn


def get_db() -> sqlite3.Connection:
    """Ағымдағы сұраныс үшін қосылым (g ішінде кэштеледі)."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Кестелерді құрады (бар болса, тимейді) және ескі қорларды жаңа схемаға көшіреді."""
    db = get_db()
    db.executescript(SCHEMA)
    # Миграция: city бағаны қосылғанға дейін жасалған қорларда ол жоқ — деректерді жоғалтпай қосамыз
    if "city" not in {r["name"] for r in db.execute("PRAGMA table_info(events)")}:
        db.execute("ALTER TABLE events ADD COLUMN city TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_city ON events(city)")


@contextmanager
def transaction():
    """BEGIN IMMEDIATE: жазу құлпын бірден алады, сондықтан орын санын тексеру
    мен тіркеуді қосу арасында басқа сұраныс кіре алмайды (race condition жоқ)."""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")
