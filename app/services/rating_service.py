"""Рейтинг: үздік еріктілер, ұйымдастырушылар, белсенді қалалар."""
from datetime import datetime

from ..database import get_db
from ..models import REG_ATTENDED, ROLE_ORGANIZER, ROLE_VOLUNTEER

TOP_N = 10
PERIODS = (("all", "Барлық уақыт"), ("month", "Осы ай"))


def _since(period: str):
    """Ай басы ('YYYY-MM-01 00:00') немесе None; іс-шара күні бойынша сүзеді."""
    if period == "month":
        return datetime.now().strftime("%Y-%m-01 00:00")
    return None


def _where(period: str):
    since = _since(period)
    return (" AND e.event_date >= ?", [since]) if since else ("", [])


def top_volunteers(period: str = "all", limit: int = TOP_N):
    extra, params = _where(period)
    sql = f"""SELECT u.full_name, u.public_code, u.id_public, COUNT(*) AS events,
                     SUM(e.hours) AS hours, COUNT(DISTINCT e.city) AS cities
              FROM registrations r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
              WHERE r.status = ? AND u.role = ? {extra}
              GROUP BY u.id ORDER BY hours DESC, events DESC, u.full_name LIMIT ?"""
    rows = get_db().execute(sql, [REG_ATTENDED, ROLE_VOLUNTEER] + params + [limit]).fetchall()
    out = []
    for i, r in enumerate(rows, 1):
        private = not r["id_public"]
        out.append({"place": i, "name": "Жасырын ерікті" if private else r["full_name"],
                    "code": None if private else r["public_code"],
                    "events": r["events"], "hours": r["hours"], "cities": r["cities"]})
    return out


def top_organizers(period: str = "all", limit: int = TOP_N):
    extra, params = _where(period)
    sql = f"""SELECT u.full_name, COUNT(DISTINCT e.id) AS events, COUNT(r.id) AS attended
              FROM events e JOIN users u ON u.id = e.organizer_id
              LEFT JOIN registrations r ON r.event_id = e.id AND r.status = ?
              WHERE u.role = ? AND e.status = 'published' {extra}
              GROUP BY u.id HAVING attended > 0
              ORDER BY attended DESC, events DESC, u.full_name LIMIT ?"""
    rows = get_db().execute(sql, [REG_ATTENDED, ROLE_ORGANIZER] + params + [limit]).fetchall()
    return [{"place": i, "name": r["full_name"], "events": r["events"], "attended": r["attended"]}
            for i, r in enumerate(rows, 1)]


def top_cities(period: str = "all", limit: int = TOP_N):
    extra, params = _where(period)
    sql = f"""SELECT e.city, COUNT(DISTINCT e.id) AS events, COUNT(r.id) AS attended
              FROM events e JOIN registrations r ON r.event_id = e.id AND r.status = ?
              WHERE e.city != '' {extra}
              GROUP BY e.city ORDER BY attended DESC, events DESC, e.city LIMIT ?"""
    rows = get_db().execute(sql, [REG_ATTENDED] + params + [limit]).fetchall()
    return [{"place": i, "city": r["city"], "events": r["events"], "attended": r["attended"]}
            for i, r in enumerate(rows, 1)]


def normalize_period(value: str) -> str:
    return value if value in {p for p, _ in PERIODS} else "all"
