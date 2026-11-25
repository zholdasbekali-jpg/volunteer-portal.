"""Іс-шараға тіркелу, бас тарту және қатысуды белгілеу."""
import sqlite3
from datetime import datetime

from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied, ValidationError
from ..models import (EVENT_PUBLISHED, REG_ABSENT, REG_ATTENDED, REG_PENDING,
                      REG_STATUSES, ROLE_ADMIN, ROLE_VOLUNTEER)
from .event_service import DATE_FMT, can_manage
from .waitlist_service import promote_next_in


class CancelResult(list):
    """Бұрынғыдай жойылған PDF жолдарының тізімі, бірақ қосымша: кезектен өткен адам."""

    def __init__(self, paths=(), promoted=None, event_id=None):
        super().__init__(paths)
        self.promoted = promoted
        self.event_id = event_id


def register(actor, event_id: int) -> int:
    """Эріктіні іс-шараға тіркейді.

    Орын санын тексеру мен INSERT бір BEGIN IMMEDIATE транзакциясында орындалады:
    екі адам бір мезгілде соңғы орынға тіркелсе, біреуі ғана өтеді.
    """
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        raise PermissionDenied("Іс-шараға тек ерікті тіркеле алады.")
    with transaction() as db:
        event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if event is None:
            raise NotFound("Іс-шара табылмады.")
        if event["status"] != EVENT_PUBLISHED:
            raise Conflict("Бұл іс-шара тоқтатылған, тіркелу жабық.")
        if event["event_date"] <= datetime.now().strftime(DATE_FMT):
            raise Conflict("Іс-шара өтіп кеткен, тіркелу мүмкін емес.")
        if db.execute("SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?",
                      (actor["id"], event_id)).fetchone():
            raise Conflict("Сіз бұл іс-шараға бұрын тіркелгенсіз.")
        taken = db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?",
                           (event_id,)).fetchone()[0]
        if taken >= event["capacity"]:
            raise Conflict("Бос орын қалмады: қатысушылардың ең көп санына жетті.")
        try:
            cur = db.execute("INSERT INTO registrations (user_id, event_id) VALUES (?, ?)",
                             (actor["id"], event_id))
        except sqlite3.IntegrityError:  # UNIQUE(user_id, event_id) соңғы қорғаныс
            raise Conflict("Сіз бұл іс-шараға бұрын тіркелгенсіз.")
        return cur.lastrowid


def cancel_registration(actor, registration_id: int) -> list:
    """Эрікті өз тіркелімінен бас тартады (орын босайды). Расталған қатысудан бас тартуға болмайды.
    Өшірілетін PDF жолдарын қайтарады (қазіргі ережеде бос тізім)."""
    with transaction() as db:
        reg = db.execute("SELECT * FROM registrations WHERE id = ?", (registration_id,)).fetchone()
        if reg is None:
            raise NotFound("Тіркелім табылмады.")
        if reg["user_id"] != actor["id"]:
            raise PermissionDenied("Тек өз тіркелімінен бас тарта аласыз.")
        if reg["status"] != REG_PENDING:
            raise Conflict("Қатысу мәртебесі белгіленген тіркелімнен бас тартуға болмайды.")
        event = db.execute("SELECT event_date FROM events WHERE id = ?", (reg["event_id"],)).fetchone()
        if event["event_date"] <= datetime.now().strftime(DATE_FMT):
            raise Conflict("Өтіп кеткен іс-шарадан бас тарту мүмкін емес.")
        db.execute("DELETE FROM registrations WHERE id = ?", (registration_id,))
        # Орын босады: күту тізіміндегі бірінші адамды осы транзакцияда тіркейміз.
        promoted = promote_next_in(db, reg["event_id"], exclude_user_id=actor["id"])
    return CancelResult([], promoted=promoted, event_id=reg["event_id"])


def set_attendance(actor, registration_id: int, status: str) -> list:
    """Ұйымдастырушы (немесе әкімші) қатысу мәртебесін белгілейді.
    'attended'-тен басқа мәртебеге ауысса, берілген сертификат жойылады.
    Жойылған PDF жолдарын қайтарады."""
    if status not in REG_STATUSES:
        raise ValidationError("Белгісіз қатысу мәртебесі.")
    removed = []
    with transaction() as db:
        row = db.execute(
            """SELECT r.id, r.status, e.organizer_id FROM registrations r
               JOIN events e ON e.id = r.event_id WHERE r.id = ?""", (registration_id,)).fetchone()
        if row is None:
            raise NotFound("Тіркелім табылмады.")
        if not can_manage({"organizer_id": row["organizer_id"]}, actor):
            raise PermissionDenied("Тек өз іс-шарасының қатысушыларын басқара аласыз.")
        db.execute("UPDATE registrations SET status = ? WHERE id = ?", (status, registration_id))
        if status != REG_ATTENDED:
            removed = [r["pdf_path"] for r in db.execute(
                "SELECT pdf_path FROM certificates WHERE registration_id = ?", (registration_id,))]
            db.execute("DELETE FROM certificates WHERE registration_id = ?", (registration_id,))
    return removed


_REG_SELECT = """
    SELECT r.id, r.status, r.registered_at, r.user_id, r.event_id,
           e.title, e.event_date, e.city, e.location, e.status AS event_status,
           c.certificate_code
    FROM registrations r
    JOIN events e ON e.id = r.event_id
    LEFT JOIN certificates c ON c.registration_id = r.id
"""


def list_for_user(user_id: int):
    return get_db().execute(_REG_SELECT + " WHERE r.user_id = ? ORDER BY e.event_date DESC",
                            (user_id,)).fetchall()


def get_user_registration(user_id: int, event_id: int):
    return get_db().execute("SELECT * FROM registrations WHERE user_id = ? AND event_id = ?",
                            (user_id, event_id)).fetchone()


def get_registration(registration_id: int):
    """Бір тіркелім (мысалы, бас тарту кезінде іс-шара мен еріктіні анықтау үшін)."""
    return get_db().execute("SELECT * FROM registrations WHERE id = ?", (registration_id,)).fetchone()


def list_for_event(actor, event_id: int):
    """Іс-шараға тіркелген эріктілер (тек иесі/әкімші көреді)."""
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        raise NotFound("Іс-шара табылмады.")
    if not can_manage(event, actor):
        raise PermissionDenied("Тек өз іс-шарасының қатысушыларын көре аласыз.")
    return db.execute(
        """SELECT r.id, r.status, r.registered_at, u.full_name, u.email,
                  c.certificate_code
           FROM registrations r JOIN users u ON u.id = r.user_id
           LEFT JOIN certificates c ON c.registration_id = r.id
           WHERE r.event_id = ? ORDER BY r.registered_at, r.id""", (event_id,)).fetchall()


def list_all(actor):
    """Барлық тіркелімдер — тек әкімші."""
    if actor is None or actor["role"] != ROLE_ADMIN:
        raise PermissionDenied("Барлық тіркелімдерді тек әкімші көре алады.")
    return get_db().execute(
        """SELECT r.id, r.status, r.registered_at, u.full_name, u.email, e.title, e.event_date
           FROM registrations r JOIN users u ON u.id = r.user_id
           JOIN events e ON e.id = r.event_id ORDER BY r.id DESC""").fetchall()
