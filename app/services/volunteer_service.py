"""Volunteer ID: жария карточка, волонтёрлік сағат, жетістіктер."""
import secrets

from ..database import get_db
from ..errors import NotFound
from ..models import REG_ATTENDED, ROLE_VOLUNTEER

# 0/O, 1/I сияқты шатасатын таңбалар жоқ
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_PREFIX = "VID-"

# (кілт, атауы, сипаттамасы, белгіше, шарт)
ACHIEVEMENTS = (
    ("first", "Алғашқы қадам", "Бірінші іс-шараға қатыстыңыз", "bi-flag", lambda s: s["events"] >= 1),
    ("active", "Белсенді", "3 іс-шараға қатыстыңыз", "bi-lightning-charge", lambda s: s["events"] >= 3),
    ("expert", "Тәжірибелі", "10 іс-шараға қатыстыңыз", "bi-trophy", lambda s: s["events"] >= 10),
    ("h10", "10 сағат", "10 волонтёрлік сағат", "bi-clock-history", lambda s: s["hours"] >= 10),
    ("h25", "25 сағат", "25 волонтёрлік сағат", "bi-hourglass-split", lambda s: s["hours"] >= 25),
    ("h50", "50 сағат", "50 волонтёрлік сағат", "bi-stars", lambda s: s["hours"] >= 50),
    ("traveler", "Саяхатшы", "3 түрлі қалада қатыстыңыз", "bi-geo-alt", lambda s: s["cities"] >= 3),
)

LEVELS = ((10, "Эксперт"), (3, "Тәжірибелі"), (1, "Белсенді"), (0, "Жаңа"))


def new_code(db) -> str:
    for _ in range(50):
        code = CODE_PREFIX + "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if db.execute("SELECT 1 FROM users WHERE public_code = ?", (code,)).fetchone() is None:
            return code
    raise RuntimeError("ID жасау мүмкін болмады")


def ensure_codes(db) -> None:
    for row in db.execute("SELECT id FROM users WHERE public_code IS NULL").fetchall():
        db.execute("UPDATE users SET public_code = ? WHERE id = ?", (new_code(db), row["id"]))


def stats_for(db, uid: int) -> dict:
    row = db.execute(
        """SELECT COUNT(*) AS events, COALESCE(SUM(e.hours), 0) AS hours,
                  COUNT(DISTINCT e.city) AS cities
           FROM registrations r JOIN events e ON e.id = r.event_id
           WHERE r.user_id = ? AND r.status = ?""", (uid, REG_ATTENDED)).fetchone()
    return {"events": row["events"], "hours": row["hours"], "cities": row["cities"]}


def level_for(events: int) -> str:
    for threshold, name in LEVELS:
        if events >= threshold:
            return name
    return LEVELS[-1][1]


def achievements_for(stats: dict) -> list:
    return [{"key": k, "title": t, "desc": d, "icon": i, "earned": bool(cond(stats))}
            for k, t, d, i, cond in ACHIEVEMENTS]


def build_card(db, user_row) -> dict:
    stats = stats_for(db, user_row["id"])
    ach = achievements_for(stats)
    return {"id": user_row["id"], "name": user_row["full_name"], "code": user_row["public_code"],
            "public": bool(user_row["id_public"]), "since": user_row["created_at"][:10],
            "stats": stats, "level": level_for(stats["events"]),
            "achievements": ach, "earned": sum(a["earned"] for a in ach)}


def get_own_card(actor) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (actor["id"],)).fetchone()
    if row["public_code"] is None:  # өте сирек: тіркелгеннен кейін ID берілмесе
        db.execute("UPDATE users SET public_code = ? WHERE id = ?", (new_code(db), row["id"]))
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id = ?", (actor["id"],)).fetchone()
    return build_card(db, row)


def get_public_card(code: str) -> dict:
    """Жария бет: тек ерікті рөлі және иесі рұқсат берсе ғана толық көрсетіледі."""
    code = (code or "").strip().upper()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE public_code = ? AND role = ?",
                     (code, ROLE_VOLUNTEER)).fetchone()
    if row is None:
        raise NotFound("Мұндай Volunteer ID табылмады.")
    if not row["id_public"]:
        return {"private": True, "code": row["public_code"]}
    return build_card(db, row)


def set_public(actor, is_public: bool) -> None:
    db = get_db()
    db.execute("UPDATE users SET id_public = ? WHERE id = ?", (1 if is_public else 0, actor["id"]))
    db.commit()
