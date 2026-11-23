"""V3: іс-шарадан кейінгі пікірлер мен бағалар (1–5).

Ерікті тек өзі қатысқан (status='attended') және өткен іс-шараға бір рет пікір қалдыра алады.
Бұл бөлек домен: rating_service еріктілер рейтингімен айналысады, мұнда іс-шара бағаланады.
"""
from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied, ValidationError
from ..models import EVENT_PUBLISHED, REG_ATTENDED, ROLE_VOLUNTEER
from .event_service import get_event, is_past

MAX_COMMENT = 2000
MIN_RATING, MAX_RATING = 1, 5


def has_review(user_id: int, event_id: int) -> bool:
    return get_db().execute("SELECT 1 FROM reviews WHERE user_id=? AND event_id=?",
                            (user_id, event_id)).fetchone() is not None


def can_review(actor, event_id: int) -> bool:
    """Беттегі форманы көрсету үшін; нақты тосқауыл add() ішінде де қайталанады."""
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        return False
    event = get_event(event_id)
    if event is None or event["status"] != EVENT_PUBLISHED or not is_past(event):
        return False
    reg = get_db().execute("SELECT status FROM registrations WHERE user_id=? AND event_id=?",
                           (actor["id"], event_id)).fetchone()
    return reg is not None and reg["status"] == REG_ATTENDED and not has_review(actor["id"], event_id)


def add(actor, event_id: int, rating, comment: str = "") -> int:
    """Пікір сақтайды; құқық пен енгізуді сервер жағында қатаң тексереді."""
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        raise PermissionDenied("Пікірді тек қатысқан ерікті қалдыра алады.")
    event = get_event(event_id)
    if event is None:
        raise NotFound("Іс-шара табылмады.")
    if event["status"] != EVENT_PUBLISHED or not is_past(event):
        raise PermissionDenied("Іс-шара өткеннен кейін ғана пікір қалдыруға болады.")
    reg = get_db().execute("SELECT status FROM registrations WHERE user_id=? AND event_id=?",
                           (actor["id"], event_id)).fetchone()
    if reg is None or reg["status"] != REG_ATTENDED:
        raise PermissionDenied("Пікірді тек қатысқан ерікті қалдыра алады.")
    try:
        value = int(rating)
    except (TypeError, ValueError):
        value = 0
    if not MIN_RATING <= value <= MAX_RATING:
        raise ValidationError("Баға 1 мен 5 арасында болуы керек.")
    text = str(comment or "").strip()
    if len(text) > MAX_COMMENT:
        raise ValidationError("Пікір 2000 таңбадан аспауы керек.")
    with transaction() as db:
        if db.execute("SELECT 1 FROM reviews WHERE user_id=? AND event_id=?",
                      (actor["id"], event_id)).fetchone():
            raise Conflict("Сіз бұл іс-шараға пікір қалдырғансыз.")
        cur = db.execute("INSERT INTO reviews (event_id, user_id, rating, comment) VALUES (?,?,?,?)",
                         (event_id, actor["id"], value, text))
        return cur.lastrowid


def list_for_event(event_id: int) -> list:
    """Пікірлер (жаңасы алдымен). Жеке профилі бар еріктінің аты жасырылады."""
    rows = get_db().execute(
        """SELECT r.id, r.rating, r.comment, r.created_at, u.full_name, u.id_public
           FROM reviews r JOIN users u ON u.id = r.user_id
           WHERE r.event_id = ? ORDER BY r.created_at DESC, r.id DESC""", (event_id,)).fetchall()
    return [dict(row) | {"author_name": row["full_name"] if row["id_public"] else "Жасырын ерікті"}
            for row in rows]


def summary(event_id: int) -> dict:
    row = get_db().execute("SELECT COUNT(*) AS n, AVG(rating) AS avg FROM reviews WHERE event_id=?",
                           (event_id,)).fetchone()
    count = row["n"]
    return {"count": count, "average": round(row["avg"], 1) if count else None}
