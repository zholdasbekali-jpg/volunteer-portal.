"""Тіркелу, аутентификация және пайдаланушыларды басқару."""
import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied, ValidationError
from .volunteer_service import new_code
from ..models import ROLES, SELF_REGISTER_ROLES, ROLE_ADMIN, ROLE_VOLUNTEER

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
MIN_PASSWORD_LEN = 8


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    email = normalize_email(email)
    if not email:
        raise ValidationError("Электрондық пошта міндетті түрде толтырылуы керек.")
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError("Электрондық пошта форматы дұрыс емес.")
    return email


def validate_password(password: str) -> None:
    if not password:
        raise ValidationError("Құпиясөз міндетті түрде толтырылуы керек.")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValidationError(f"Құпиясөз кемінде {MIN_PASSWORD_LEN} таңбадан тұруы керек.")
    if not (re.search(r"[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]", password) and re.search(r"\d", password)):
        raise ValidationError("Құпиясөзде кемінде бір әріп және бір цифр болуы керек.")


def register_user(full_name: str, email: str, password: str, role: str = ROLE_VOLUNTEER) -> int:
    """Жаңа пайдаланушыны тіркейді. Парольді Werkzeug арқылы хештейді. Жаңа id қайтарады."""
    full_name = " ".join((full_name or "").split())
    if len(full_name) < 2:
        raise ValidationError("Аты-жөні міндетті (кемінде 2 таңба).")
    if len(full_name) > 120:
        raise ValidationError("Аты-жөні тым ұзын (ең көбі 120 таңба).")
    email = validate_email(email)
    validate_password(password)
    if role not in SELF_REGISTER_ROLES:
        raise ValidationError("Бұл рөлмен тіркелуге болмайды.")
    try:
        with transaction() as db:
            cur = db.execute(
                "INSERT INTO users (full_name, email, password_hash, role, public_code) VALUES (?, ?, ?, ?, ?)",
                (full_name, email, generate_password_hash(password), role, new_code(db)),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        # UNIQUE(email) — бір email-мен қайта тіркелуге жол жоқ
        raise Conflict("Бұл электрондық пошта бұрын тіркелген.")


def create_user_unchecked(full_name, email, password, role):
    """Жүйелік пайдаланушыны (мыс. әкімші) жасау: seed/CLI үшін. Рөл шектеуі жоқ."""
    if role not in ROLES:
        raise ValidationError("Белгісіз рөл.")
    email = validate_email(email)
    validate_password(password)
    try:
        with transaction() as db:
            cur = db.execute(
                "INSERT INTO users (full_name, email, password_hash, role, public_code) VALUES (?, ?, ?, ?, ?)",
                (full_name.strip(), email, generate_password_hash(password), role, new_code(db)),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise Conflict("Бұл электрондық пошта бұрын тіркелген.")


def authenticate(email: str, password: str):
    """Email мен парольді тексереді. Сәтті болса — пайдаланушы жолы, әйтпесе ValidationError.
    Қате хабарламасы email немесе пароль екенін ашпайды (user enumeration алдын алу)."""
    email = normalize_email(email)
    if not email or not password:
        raise ValidationError("Электрондық пошта мен құпиясөзді енгізіңіз.")
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        raise ValidationError("Электрондық пошта немесе құпиясөз қате.")
    return row


def get_user(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users():
    return get_db().execute(
        """SELECT u.id, u.full_name, u.email, u.role, u.created_at,
                  (SELECT COUNT(*) FROM registrations r WHERE r.user_id = u.id) AS reg_count,
                  (SELECT COUNT(*) FROM events e WHERE e.organizer_id = u.id) AS event_count
           FROM users u ORDER BY u.id"""
    ).fetchall()


def _require_admin(actor):
    if actor is None or actor["role"] != ROLE_ADMIN:
        raise PermissionDenied("Бұл әрекетке тек әкімшінің құқығы бар.")


def set_user_role(actor, user_id: int, new_role: str) -> None:
    _require_admin(actor)
    if new_role not in ROLES:
        raise ValidationError("Белгісіз рөл.")
    if actor["id"] == user_id:
        raise ValidationError("Өз рөліңізді өзгертуге болмайды.")
    with transaction() as db:
        if db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            raise NotFound("Пайдаланушы табылмады.")
        db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))


def delete_user(actor, user_id: int) -> list:
    """Пайдаланушыны жояды. Байланысты жазбалар CASCADE арқылы жойылады.
    Жойылған сертификат PDF жолдарын қайтарады (файлдарды шақырушы өшіреді)."""
    _require_admin(actor)
    if actor["id"] == user_id:
        raise ValidationError("Өзіңізді жоюға болмайды.")
    with transaction() as db:
        if db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            raise NotFound("Пайдаланушы табылмады.")
        paths = [r["pdf_path"] for r in db.execute(
            """SELECT c.pdf_path FROM certificates c
               JOIN registrations r ON r.id = c.registration_id
               JOIN events e ON e.id = r.event_id
               WHERE r.user_id = ? OR e.organizer_id = ?""", (user_id, user_id))]
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return paths
