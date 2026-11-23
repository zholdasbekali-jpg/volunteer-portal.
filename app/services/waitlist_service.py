"""V3: күту тізімі (орын қалмаған іс-шараға кезек).

Тіркелімнен бас тартумен бір транзакцияда бірінші күтушіні қатысушы етеміз:
осылайша бос орын екінші сұранысқа кетіп кетпейді (race condition жоқ).
"""
from datetime import datetime

from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied
from ..models import EVENT_PUBLISHED, ROLE_ADMIN, ROLE_VOLUNTEER
from .event_service import DATE_FMT, can_manage


def _event(db, event_id):
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        raise NotFound("Іс-шара табылмады.")
    return event


def join(actor, event_id: int) -> int:
    """Еріктіні күту тізіміне қосады (тек орын қалмаған, өтпеген іс-шараға)."""
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        raise PermissionDenied("Күту тізіміне тек ерікті қосыла алады.")
    with transaction() as db:
        event = _event(db, event_id)
        if event["status"] != EVENT_PUBLISHED:
            raise Conflict("Бұл іс-шара тоқтатылған, тіркелу жабық.")
        if event["event_date"] <= datetime.now().strftime(DATE_FMT):
            raise Conflict("Іс-шара өтіп кеткен, тіркелу мүмкін емес.")
        if db.execute("SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?",
                      (actor["id"], event_id)).fetchone():
            raise Conflict("Сіз бұл іс-шараға бұрын тіркелгенсіз.")
        taken = db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event_id,)).fetchone()[0]
        if taken < event["capacity"]:
            raise Conflict("Бұл іс-шараға орын бар, тіркеліңіз.")
        if db.execute("SELECT 1 FROM waitlist WHERE user_id = ? AND event_id = ?",
                      (actor["id"], event_id)).fetchone():
            raise Conflict("Сіз бұл іс-шараның күту тізімінде барсыз.")
        cur = db.execute("INSERT INTO waitlist (user_id, event_id) VALUES (?, ?)",
                         (actor["id"], event_id))
        return cur.lastrowid


def leave(actor, event_id: int) -> None:
    """Ерікті өз кезегінен шығады."""
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        raise PermissionDenied("Күту тізіміне тек ерікті қосыла алады.")
    with transaction() as db:
        cur = db.execute("DELETE FROM waitlist WHERE user_id = ? AND event_id = ?",
                         (actor["id"], event_id))
        if cur.rowcount == 0:
            raise Conflict("Күту тізіміңізде сіз жоқсыз.")


def position(user_id: int, event_id: int) -> int | None:
    """Орныңыз (1-ден басталады) немесе тізімде болмаса None."""
    rows = get_db().execute(
        "SELECT user_id FROM waitlist WHERE event_id = ? ORDER BY created_at, id", (event_id,)).fetchall()
    for index, row in enumerate(rows, 1):
        if row["user_id"] == user_id:
            return index
    return None


def list_for_event(actor, event_id: int) -> list:
    """Іс-шара күту тізімі (тек иесі/әкімші көреді), кезек нөмерімен бірге."""
    db = get_db()
    event = _event(db, event_id)
    if not can_manage(event, actor):
        raise PermissionDenied("Тек өз іс-шараңыздың күту тізімін көре аласыз.")
    rows = db.execute(
        """SELECT w.id, w.user_id, w.created_at, u.full_name, u.email
           FROM waitlist w JOIN users u ON u.id = w.user_id
           WHERE w.event_id = ? ORDER BY w.created_at, w.id""", (event_id,)).fetchall()
    return [dict(row) | {"position": i} for i, row in enumerate(rows, 1)]


def list_for_user(user_id: int) -> list:
    """Еріктінің барлық кезектері (кабинетте көрсету үшін)."""
    rows = get_db().execute(
        """SELECT w.event_id, w.created_at, e.title, e.event_date, e.city, e.location, e.status AS event_status
           FROM waitlist w JOIN events e ON e.id = w.event_id
           WHERE w.user_id = ? ORDER BY e.event_date""", (user_id,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["position"] = position(user_id, row["event_id"])
        result.append(item)
    return result


def promote_next_in(db, event_id: int, exclude_user_id: int | None = None) -> dict | None:
    """Бос орынға бірінші күтушіні тіркейді. TEXT/BEGIN IMMEDIATE ішінде шақырылады.

    Қайтарған сөздіктегі user_id арқылы шақырушы хабарлама жібереді.
    """
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None or event["status"] != EVENT_PUBLISHED:
        return None
    if event["event_date"] <= datetime.now().strftime(DATE_FMT):
        return None
    taken = db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event_id,)).fetchone()[0]
    if taken >= event["capacity"]:
        return None
    row = db.execute(
        """SELECT * FROM waitlist WHERE event_id = ? AND user_id != ?
           ORDER BY created_at, id LIMIT 1""", (event_id, exclude_user_id or -1)).fetchone()
    if row is None:
        return None
    db.execute("DELETE FROM waitlist WHERE id = ?", (row["id"],))
    if db.execute("SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?",
                  (row["user_id"], event_id)).fetchone():
        return None
    cur = db.execute("INSERT INTO registrations (user_id, event_id) VALUES (?, ?)",
                     (row["user_id"], event_id))
    return {"user_id": row["user_id"], "event_id": event_id, "registration_id": cur.lastrowid}
