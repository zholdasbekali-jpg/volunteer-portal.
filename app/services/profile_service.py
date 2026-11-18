"""Жеке кабинет: профиль, құпиясөзді ауыстыру, рөлге қарай жиынтық."""
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import get_db, transaction
from ..errors import NotFound, PermissionDenied, ValidationError
from ..models import (EVENT_PUBLISHED, REG_ATTENDED, REG_PENDING, ROLE_ADMIN, ROLE_ORGANIZER,
                      ROLE_VOLUNTEER, ROLES)
from .auth_service import validate_password
from .event_service import now_str

UPCOMING_LIMIT = 5


def get_profile(actor) -> dict:
    row = get_db().execute("SELECT id, full_name, email, role, created_at FROM users WHERE id = ?",
                           (actor["id"],)).fetchone()
    if row is None:
        raise NotFound("Пайдаланушы табылмады.")
    return dict(row)


def update_name(actor, full_name: str) -> None:
    full_name = " ".join((full_name or "").split())
    if len(full_name) < 2:
        raise ValidationError("Аты-жөні міндетті (кемінде 2 таңба).")
    if len(full_name) > 120:
        raise ValidationError("Аты-жөні тым ұзын (ең көбі 120 таңба).")
    with transaction() as db:
        db.execute("UPDATE users SET full_name = ? WHERE id = ?", (full_name, actor["id"]))


def change_password(actor, current: str, new: str, confirm: str) -> None:
    if not current or not new:
        raise ValidationError("Барлық өрісті толтырыңыз.")
    with transaction() as db:
        row = db.execute("SELECT password_hash FROM users WHERE id = ?", (actor["id"],)).fetchone()
        if row is None:
            raise NotFound("Пайдаланушы табылмады.")
        if not check_password_hash(row["password_hash"], current):
            raise ValidationError("Қазіргі құпиясөз қате.")
        validate_password(new)
        if new != confirm:
            raise ValidationError("Жаңа құпиясөз бен растау сәйкес емес.")
        if new == current:
            raise ValidationError("Жаңа құпиясөз ескісінен өзгеше болуы керек.")
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), actor["id"]))


def _volunteer(db, uid):
    row = db.execute("""SELECT COUNT(*) AS total,
                               COALESCE(SUM(status = ?), 0) AS attended,
                               COALESCE(SUM(status = ?), 0) AS pending
                        FROM registrations WHERE user_id = ?""", (REG_ATTENDED, REG_PENDING, uid)).fetchone()
    certs = db.execute("""SELECT COUNT(*) FROM certificates c JOIN registrations r ON r.id = c.registration_id
                          WHERE r.user_id = ?""", (uid,)).fetchone()[0]
    upcoming = db.execute("""SELECT e.id, e.title, e.event_date, e.city FROM registrations r
                             JOIN events e ON e.id = r.event_id
                             WHERE r.user_id = ? AND e.status = ? AND e.event_date >= ?
                             ORDER BY e.event_date LIMIT ?""",
                          (uid, EVENT_PUBLISHED, now_str(), UPCOMING_LIMIT)).fetchall()
    return {"stats": [("Тіркелген іс-шара", row["total"]), ("Қатысқан", row["attended"]),
                      ("Қатысуы күтілуде", row["pending"]), ("Сертификат", certs)],
            "upcoming": [dict(r) for r in upcoming]}


def _organizer(db, uid):
    ev = db.execute("""SELECT COUNT(*) AS total, COALESCE(SUM(status = ?), 0) AS published
                       FROM events WHERE organizer_id = ?""", (EVENT_PUBLISHED, uid)).fetchone()
    reg = db.execute("""SELECT COUNT(*) AS total, COALESCE(SUM(r.status = ?), 0) AS attended
                        FROM registrations r JOIN events e ON e.id = r.event_id
                        WHERE e.organizer_id = ?""", (REG_ATTENDED, uid)).fetchone()
    upcoming = db.execute("""SELECT e.id, e.title, e.event_date, e.city,
                                    (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered,
                                    e.capacity
                             FROM events e WHERE e.organizer_id = ? AND e.status = ? AND e.event_date >= ?
                             ORDER BY e.event_date LIMIT ?""",
                          (uid, EVENT_PUBLISHED, now_str(), UPCOMING_LIMIT)).fetchall()
    return {"stats": [("Менің іс-шараларым", ev["total"]), ("Жарияланған", ev["published"]),
                      ("Барлық тіркелім", reg["total"]), ("Қатысты", reg["attended"])],
            "upcoming": [dict(r) for r in upcoming]}


def _admin(db):
    counts = {r["role"]: r["n"] for r in db.execute("SELECT role, COUNT(*) AS n FROM users GROUP BY role")}
    ev = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    reg = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    return {"stats": [("Пайдаланушы", sum(counts.get(r, 0) for r in ROLES)),
                      ("Ерікті", counts.get(ROLE_VOLUNTEER, 0)),
                      ("Ұйымдастырушы", counts.get(ROLE_ORGANIZER, 0)),
                      ("Іс-шара", ev), ("Тіркелім", reg)],
            "upcoming": [], "latest_users": [dict(r) for r in db.execute(
                "SELECT id, full_name, email, role, created_at FROM users ORDER BY id DESC LIMIT 5")]}


def cabinet_summary(actor) -> dict:
    if actor is None:
        raise PermissionDenied("Кіру қажет.")
    db = get_db()
    if actor["role"] == ROLE_ADMIN:
        return _admin(db)
    if actor["role"] == ROLE_ORGANIZER:
        return _organizer(db, actor["id"])
    return _volunteer(db, actor["id"])
