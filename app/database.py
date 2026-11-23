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
    approval      TEXT NOT NULL DEFAULT 'approved',  -- V3: organizer үшін 'pending'/'approved'/'rejected'
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

CREATE TABLE IF NOT EXISTS login_attempts (
    key          TEXT PRIMARY KEY,          -- 'e:<email>' немесе 'i:<ip>'
    fails        INTEGER NOT NULL DEFAULT 0,
    window_start REAL NOT NULL,
    locked_until REAL NOT NULL DEFAULT 0
);

-- V3: орын қалмағанда күту тізімі, еріктінің таңдаулы іс-шаралары,
-- іс-шарадан кейінгі пікірлер мен әкімші әрекеттерінің журналы.
CREATE TABLE IF NOT EXISTS waitlist (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (user_id, event_id)
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (user_id, event_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action       TEXT NOT NULL,
    target_type  TEXT NOT NULL DEFAULT '',
    target_id    INTEGER,
    details      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_events_date       ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_events_organizer  ON events(organizer_id);
CREATE INDEX IF NOT EXISTS idx_reg_event         ON registrations(event_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_event    ON waitlist(event_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_reviews_event     ON reviews(event_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user    ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created     ON audit_log(created_at DESC);
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


def _add_column(db, table: str, column: str, ddl: str) -> None:
    """ALTER TABLE ... ADD COLUMN. Екі gunicorn worker бір мезгілде іске қосылса, екіншісі
    "duplicate column name" алады: бұл қате емес, баған бұрыннан бар деген сөз."""
    if column in {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}:
        return
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except sqlite3.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise


def init_db() -> None:
    """Кестелерді құрады (бар болса, тимейді) және ескі қорларды жаңа схемаға көшіреді."""
    db = get_db()
    db.executescript(SCHEMA)
    # Миграция: city бағаны қосылғанға дейін жасалған қорларда ол жоқ — деректерді жоғалтпай қосамыз
    _add_column(db, "events", "city", "TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_city ON events(city)")
    # V2: іс-шара ұзақтығы (волонтёрлік сағат) және ерікті жария ID-і
    _add_column(db, "events", "hours", "INTEGER NOT NULL DEFAULT 3")
    _add_column(db, "users", "public_code", "TEXT")
    _add_column(db, "users", "id_public", "INTEGER NOT NULL DEFAULT 1")
    _add_column(db, "events", "category", "TEXT NOT NULL DEFAULT 'other'")  # V2: іс-шара санаты
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_category ON events(category)")
    _add_column(db, "users", "lang", "TEXT")  # V2: таңдаған интерфейс тілі (kk/ru/en); хаттар да осы тілде
    # V3: ұйымдастырушыны әкімші мақұлдайды. Ескі пайдаланушылардың бәрі мақұлдалған болып саналады,
    # сондықтан DEFAULT = 'approved'; мәндер сервис деңгейінде тексеріледі.
    _add_column(db, "users", "approval", "TEXT NOT NULL DEFAULT 'approved'")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_public_code ON users(public_code)")
    from .services.volunteer_service import ensure_codes  # ескі пайдаланушыларға ID береміз
    ensure_codes(db)
    db.commit()


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
