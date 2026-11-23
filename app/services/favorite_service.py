"""V3: еріктінің таңдаулы іс-шаралары (favorites).

Күту тізімінен айырмашылығы: бұл жеке тізім, басқа пайдаланушыға көрінбейді.
"""
from ..database import get_db, transaction
from ..errors import NotFound, PermissionDenied
from ..models import ROLE_VOLUNTEER


def _check_actor(actor) -> None:
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        raise PermissionDenied("Таңдаулылар тек еріктілерге қолжетімді.")


def add(actor, event_id: int) -> bool:
    """Қосады; егер бұрын болса, қайта қоспайды (идемпотентті)."""
    _check_actor(actor)
    with transaction() as db:
        if db.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone() is None:
            raise NotFound("Іс-шара табылмады.")
        cur = db.execute("INSERT OR IGNORE INTO favorites (user_id, event_id) VALUES (?, ?)",
                         (actor["id"], event_id))
        return cur.rowcount > 0


def remove(actor, event_id: int) -> bool:
    """Шығарады; жазба болмаса False."""
    _check_actor(actor)
    with transaction() as db:
        cur = db.execute("DELETE FROM favorites WHERE user_id = ? AND event_id = ?",
                         (actor["id"], event_id))
        return cur.rowcount > 0


def ids_for_user(user_id: int) -> set:
    return {row["event_id"] for row in get_db().execute(
        "SELECT event_id FROM favorites WHERE user_id = ?", (user_id,)).fetchall()}


def is_favorite(actor, event_id: int) -> bool:
    if actor is None:
        return False
    try:
        role = actor["role"]
        uid = actor["id"]
    except (KeyError, TypeError):
        return False
    if role != ROLE_VOLUNTEER:
        return False
    return event_id in ids_for_user(uid)


def list_for_user(user_id: int) -> list:
    return [dict(row) for row in get_db().execute(
        """SELECT f.event_id, f.created_at, e.title, e.event_date, e.city, e.location,
                  e.status AS event_status, e.category
           FROM favorites f JOIN events e ON e.id = f.event_id
           WHERE f.user_id = ? ORDER BY e.event_date""", (user_id,)).fetchall()]
