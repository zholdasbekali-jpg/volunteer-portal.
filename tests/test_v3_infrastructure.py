"""V3 инфрақұрылымы: жаңа кестелер, ескі қорды көшіру, пошта конфигурациясы."""
import sqlite3

from app import create_app
from config import TestConfig
from conftest import PASSWORD


def _tables(db):
    return {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_new_tables_exist_on_fresh_db(ctx):
    from app.database import get_db
    db = get_db()
    tables = _tables(db)
    assert {"waitlist", "favorites", "reviews", "audit_log"} <= tables
    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
    assert "approval" in cols
    # fresh DB has no users; DEFAULT must be applied when one is inserted
    db.execute("INSERT INTO users (full_name,email,password_hash,role) VALUES ('Сынақ','t@x.test','x','volunteer')")
    assert db.execute("SELECT approval FROM users WHERE email='t@x.test'").fetchone()["approval"] == "approved"


def test_existing_users_are_approved_after_migration(tmp_path):
    path = str(tmp_path / "legacy.db")
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'volunteer',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', location TEXT NOT NULL, event_date TEXT NOT NULL,
        capacity INTEGER NOT NULL, organizer_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'published',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        INSERT INTO users (full_name,email,password_hash,role) VALUES ('Ескі ерікті','old@x.test','x','volunteer');""")
    con.commit()
    con.close()

    app = create_app(TestConfig, DATABASE=path, CERTIFICATE_DIR=str(tmp_path / "certs"))
    with app.app_context():
        from app.database import get_db
        db = get_db()
        assert db.execute("SELECT approval FROM users WHERE email='old@x.test'").fetchone()["approval"] == "approved"
        assert {"waitlist", "favorites", "reviews", "audit_log"} <= _tables(db)
        # екінші іске қосу қайталанатын (идемпотентті) болуы керек
        from app.database import init_db
        init_db()


def test_mail_config_is_safe_by_default():
    assert TestConfig.MAIL_ENABLED is False
    assert TestConfig.MAIL_SERVER == "localhost"
    assert TestConfig.MAIL_PORT == 25
    assert TestConfig.MAIL_REMINDER_DAYS == 3
