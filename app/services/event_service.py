"""Іс-шаралар: құру, өңдеу, тоқтату, жою, іздеу."""
from datetime import datetime

from ..database import get_db, transaction
from ..errors import NotFound, PermissionDenied, ValidationError
from ..models import EVENT_CANCELLED, EVENT_PUBLISHED, ROLE_ADMIN, ROLE_ORGANIZER

DATE_FMT = "%Y-%m-%d %H:%M"
MAX_CAPACITY = 10000

# Каталог пен басқару беттері үшін ортақ SELECT: бос орын саны бірден есептеледі
_EVENT_SELECT = """
    SELECT e.*, u.full_name AS organizer_name,
           (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count,
           (SELECT COUNT(*) FROM registrations r
             WHERE r.event_id = e.id AND r.status = 'attended') AS attended_count
    FROM events e JOIN users u ON u.id = e.organizer_id
"""


def parse_event_date(value: str) -> datetime:
    """HTML datetime-local ('2026-05-01T10:00') және 'YYYY-MM-DD HH:MM' форматтарын қабылдайды."""
    value = (value or "").strip().replace("T", " ")
    try:
        return datetime.strptime(value, DATE_FMT)
    except ValueError:
        raise ValidationError("Күні мен уақыты дұрыс емес. Мысалы: 2026-12-31 10:00.")


def validate_event_data(data: dict, require_future: bool) -> dict:
    """Форма деректерін серверде тексеріп, таза сөздік қайтарады."""
    title = " ".join((data.get("title") or "").split())
    description = (data.get("description") or "").strip()
    location = " ".join((data.get("location") or "").split())
    if len(title) < 3:
        raise ValidationError("Атауы міндетті (кемінде 3 таңба).")
    if len(title) > 150:
        raise ValidationError("Атауы тым ұзын (ең көбі 150 таңба).")
    if not location:
        raise ValidationError("Өтетін орны міндетті түрде көрсетілуі керек.")
    if len(location) > 200:
        raise ValidationError("Орын атауы тым ұзын (ең көбі 200 таңба).")
    if len(description) > 5000:
        raise ValidationError("Сипаттама тым ұзын (ең көбі 5000 таңба).")
    when = parse_event_date(data.get("event_date"))
    if require_future and when <= datetime.now():
        raise ValidationError("Іс-шара күні болашақта болуы керек.")
    try:
        capacity = int(str(data.get("capacity", "")).strip())
    except ValueError:
        raise ValidationError("Қатысушылардың ең көп саны бүтін сан болуы керек.")
    if capacity < 1 or capacity > MAX_CAPACITY:
        raise ValidationError(f"Қатысушылар саны 1 мен {MAX_CAPACITY} аралығында болуы керек.")
    return {"title": title, "description": description, "location": location,
            "event_date": when.strftime(DATE_FMT), "capacity": capacity}


def can_manage(event, actor) -> bool:
    """Іс-шараны басқару құқығы: оның ұйымдастырушысы немесе әкімші."""
    if actor is None:
        return False
    if actor["role"] == ROLE_ADMIN:
        return True
    return actor["role"] == ROLE_ORGANIZER and event["organizer_id"] == actor["id"]


def _load_for_manage(db, event_id, actor):
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        raise NotFound("Іс-шара табылмады.")
    if not can_manage(event, actor):
        raise PermissionDenied("Тек өз іс-шараларыңызды басқара аласыз.")
    return event


def create_event(actor, data: dict) -> int:
    if actor is None or actor["role"] not in (ROLE_ORGANIZER, ROLE_ADMIN):
        raise PermissionDenied("Іс-шараны тек ұйымдастырушы құра алады.")
    clean = validate_event_data(data, require_future=True)
    with transaction() as db:
        cur = db.execute(
            """INSERT INTO events (title, description, location, event_date, capacity, organizer_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (clean["title"], clean["description"], clean["location"],
             clean["event_date"], clean["capacity"], actor["id"]),
        )
        return cur.lastrowid


def update_event(actor, event_id: int, data: dict) -> None:
    clean = validate_event_data(data, require_future=False)
    with transaction() as db:
        _load_for_manage(db, event_id, actor)
        taken = db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?",
                           (event_id,)).fetchone()[0]
        if clean["capacity"] < taken:
            raise ValidationError(
                f"Қатысушылар санын {taken}-тен азайтуға болмайды: осынша эріктілер тіркелген.")
        db.execute(
            """UPDATE events SET title = ?, description = ?, location = ?,
                                 event_date = ?, capacity = ? WHERE id = ?""",
            (clean["title"], clean["description"], clean["location"],
             clean["event_date"], clean["capacity"], event_id),
        )


def cancel_event(actor, event_id: int) -> None:
    """Іс-шараны тоқтату (деректер сақталады, тіркелу жабылады)."""
    with transaction() as db:
        _load_for_manage(db, event_id, actor)
        db.execute("UPDATE events SET status = ? WHERE id = ?", (EVENT_CANCELLED, event_id))


def restore_event(actor, event_id: int) -> None:
    with transaction() as db:
        _load_for_manage(db, event_id, actor)
        db.execute("UPDATE events SET status = ? WHERE id = ?", (EVENT_PUBLISHED, event_id))


def delete_event(actor, event_id: int) -> list:
    """Іс-шараны және оның тіркелімдерін жояды. Өшірілетін PDF жолдарын қайтарады."""
    with transaction() as db:
        _load_for_manage(db, event_id, actor)
        paths = [r["pdf_path"] for r in db.execute(
            """SELECT c.pdf_path FROM certificates c
               JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?""",
            (event_id,))]
        db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return paths


def get_event(event_id: int):
    return get_db().execute(_EVENT_SELECT + " WHERE e.id = ?", (event_id,)).fetchone()


def now_str() -> str:
    return datetime.now().strftime(DATE_FMT)


def is_past(event) -> bool:
    return parse_event_date(event["event_date"]) <= datetime.now()


def search_events(q: str = "", date: str = "", status: str = ""):
    """Каталог. q — атауы бойынша іздеу; date — 'YYYY-MM-DD'; status:
    '' (жарияланғандар), 'upcoming', 'past', 'cancelled'. Тізім күні бойынша сұрыпталады."""
    now = datetime.now().strftime(DATE_FMT)
    sql = _EVENT_SELECT + " WHERE 1=1"
    params = []
    if status == "cancelled":
        sql += " AND e.status = ?"
        params.append(EVENT_CANCELLED)
    else:
        sql += " AND e.status = ?"
        params.append(EVENT_PUBLISHED)
        if status == "upcoming":
            sql += " AND e.event_date > ?"
            params.append(now)
        elif status == "past":
            sql += " AND e.event_date <= ?"
            params.append(now)
    q = (q or "").strip()
    if q:
        # LIKE арнайы таңбаларын экрандаймыз (% және _ әріп ретінде ізделеді)
        escaped = q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " AND (PYLOWER(e.title) LIKE ? ESCAPE '\\' OR PYLOWER(e.location) LIKE ? ESCAPE '\\')"
        params += [f"%{escaped}%", f"%{escaped}%"]
    date = (date or "").strip()
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValidationError("Сүзгі күні дұрыс емес.")
        sql += " AND substr(e.event_date, 1, 10) = ?"
        params.append(date)
    sql += " ORDER BY e.event_date"
    rows = get_db().execute(sql, params).fetchall()
    return rows


def split_upcoming_past(events):
    now = datetime.now().strftime(DATE_FMT)
    upcoming = [e for e in events if e["event_date"] > now]
    past = [e for e in events if e["event_date"] <= now][::-1]  # жаңасы алдымен
    return upcoming, past


def list_managed_events(actor):
    """Ұйымдастырушы — өз іс-шаралары; әкімші — барлығы."""
    sql = _EVENT_SELECT
    params = ()
    if actor["role"] != ROLE_ADMIN:
        sql += " WHERE e.organizer_id = ?"
        params = (actor["id"],)
    sql += " ORDER BY e.event_date DESC"
    return get_db().execute(sql, params).fetchall()
