"""V3: журнал әкімші әрекеттері (audit log).

Әрекеттер кодпен сақталады (мысалы user.role_changed), ал атауы қазақша каталогта:
ол *_('...') арқылы қалған екі тілге аударылады. Журнал тек оқу үшін, өшіру қолжетімсіз.
"""
from ..database import get_db, transaction
from ..errors import ValidationError

AUDIT_ACTIONS = {
    "user.role_changed": "Пайдаланушы рөлі өзгертілді",
    "user.approved": "Ұйымдастырушы мақұлдалды",
    "user.rejected": "Ұйымдастырушы қабылданбады",
    "user.deleted": "Пайдаланушы жойылды",
    "event.created": "Іс-шара құрылды",
    "event.updated": "Іс-шара өзгертілді",
    "event.cancelled": "Іс-шара тоқтатылды",
    "event.restored": "Іс-шара қайта жарияланды",
    "event.deleted": "Іс-шара жойылды",
    "registration.status_changed": "Қатысу мәртебесі өзгертілді",
}

LIMIT = 200


def log(actor, action: str, target_type: str = "", target_id=None, details: str = "") -> int:
    if action not in AUDIT_ACTIONS:
        raise ValidationError("Белгісіз аудит әрекеті.")
    actor_id = actor["id"] if actor is not None else None
    with transaction() as db:
        cur = db.execute(
            """INSERT INTO audit_log (actor_id, action, target_type, target_id, details)
               VALUES (?, ?, ?, ?, ?)""",
            (actor_id, action, target_type or "", target_id, str(details or "")[:500]))
        return cur.lastrowid


def list_recent(q: str = "", action: str = "", limit: int = LIMIT) -> list:
    where, params = [], []
    if action in AUDIT_ACTIONS:
        where.append("a.action = ?")
        params.append(action)
    needle = (q or "").strip()
    if needle:
        where.append("(a.action LIKE ? OR a.details LIKE ? OR a.target_type LIKE ? OR u.full_name LIKE ?)")
        params.extend([f"%{needle}%"] * 4)
    sql = """SELECT a.*, u.full_name AS actor_name FROM audit_log a
             LEFT JOIN users u ON u.id = a.actor_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(int(limit))
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]
