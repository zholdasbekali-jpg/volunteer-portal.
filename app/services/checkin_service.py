"""QR арқылы өзін-өзі белгілеу (self check-in).

Ұйымдастырушы экранда динамикалық QR көрсетеді: оның ішіндегі белгі (token) әр 30 секунд сайын
өзгереді және ~90 секундтан кейін жарамсыз болады. Сондықтан QR суретке түсіріп, іс-шарада жоқ
адамға жіберу көмектеспейді. Ерікті тіркелген болуы керек, белгі HMAC-SHA256 арқылы қол қойылған.
"""
import hashlib
import hmac
import re
import time
from datetime import datetime, timedelta

from flask import current_app

from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied, ValidationError
from ..models import EVENT_PUBLISHED, REG_ATTENDED, ROLE_VOLUNTEER
from .event_service import DATE_FMT, can_manage

STEP_SECONDS = 30          # белгі әр 30 секунд сайын жаңарады
VALID_STEPS_BACK = 2       # ағымдағы және 2 алдыңғы қадам қабылданады (~90 с)
OPENS_BEFORE = timedelta(hours=2)    # іс-шарадан 2 сағат бұрын ашылады
CLOSES_AFTER = timedelta(hours=24)   # басталғаннан 24 сағаттан кейін жабылады
TOKEN_RE = re.compile(r"(\d{1,9})\.(\d{1,12})\.([0-9a-f]{16})")


def _sign(event_id: int, step: int) -> str:
    key = current_app.config["SECRET_KEY"]
    key = key.encode() if isinstance(key, str) else key
    return hmac.new(key, f"checkin:{event_id}:{step}".encode(), hashlib.sha256).hexdigest()[:16]


def make_token(event_id: int, now: float | None = None) -> str:
    step = int((time.time() if now is None else now) // STEP_SECONDS)
    return f"{event_id}.{step}.{_sign(event_id, step)}"


def extract_token(text: str) -> str | None:
    """QR мәтінінен (толық сілтеме немесе белгінің өзі) белгіні алады."""
    m = TOKEN_RE.search(text or "")
    return m.group(0) if m else None


def parse_token(token: str, now: float | None = None) -> int:
    """Белгі дұрыс әрі жаңа болса, event_id қайтарады; әйтпесе ValidationError."""
    m = TOKEN_RE.fullmatch(token or "")
    if not m:
        raise ValidationError("QR жарамсыз.")
    event_id, step = int(m.group(1)), int(m.group(2))
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    if not hmac.compare_digest(m.group(3), _sign(event_id, step)):
        raise ValidationError("QR жарамсыз.")
    if not current - VALID_STEPS_BACK <= step <= current:
        raise ValidationError("QR ескірген. Ұйымдастырушы экранындағы жаңа QR-ды сканерлеңіз.")
    return event_id


def get_event_for_token(token: str, now: float | None = None):
    event_id = parse_token(token, now)
    event = get_db().execute("SELECT id, title, event_date, city, status FROM events WHERE id = ?",
                             (event_id,)).fetchone()
    if event is None:
        raise NotFound("Іс-шара табылмады.")
    return event


def check_in(actor, token: str, now: float | None = None, clock: datetime | None = None) -> dict:
    """Ерікті өзін қатысты деп белгілейді. Нәтиже: {'event': ..., 'already': bool}."""
    if actor is None or actor["role"] != ROLE_VOLUNTEER:
        raise PermissionDenied("QR арқылы тек ерікті белгіленеді.")
    event_id = parse_token(token, now)
    clock = clock or datetime.now()
    with transaction() as db:
        event = db.execute("SELECT id, title, event_date, status FROM events WHERE id = ?",
                           (event_id,)).fetchone()
        if event is None:
            raise NotFound("Іс-шара табылмады.")
        if event["status"] != EVENT_PUBLISHED:
            raise Conflict("Іс-шара белсенді емес.")
        start = datetime.strptime(event["event_date"], DATE_FMT)
        if clock < start - OPENS_BEFORE:
            raise Conflict("Белгілеу іс-шарадан 2 сағат бұрын ашылады.")
        if clock > start + CLOSES_AFTER:
            raise Conflict("Белгілеу уақыты аяқталды.")
        reg = db.execute("SELECT id, status FROM registrations WHERE user_id = ? AND event_id = ?",
                         (actor["id"], event_id)).fetchone()
        if reg is None:
            raise Conflict("Сіз бұл іс-шараға тіркелмегенсіз.")
        if reg["status"] == REG_ATTENDED:
            return {"event": event, "already": True}
        db.execute("UPDATE registrations SET status = ? WHERE id = ?", (REG_ATTENDED, reg["id"]))
    return {"event": event, "already": False}


def attendance_counts(actor, event_id: int) -> dict:
    """Ұйымдастырушы экраны үшін: қанша адам тіркелген және белгіленген."""
    db = get_db()
    event = db.execute("SELECT id, organizer_id, title, event_date FROM events WHERE id = ?",
                       (event_id,)).fetchone()
    if event is None:
        raise NotFound("Іс-шара табылмады.")
    if not can_manage({"organizer_id": event["organizer_id"]}, actor):
        raise PermissionDenied("Тек өз іс-шараңыз үшін.")
    row = db.execute("""SELECT COUNT(*) AS total,
                               COALESCE(SUM(status = ?), 0) AS attended
                        FROM registrations WHERE event_id = ?""", (REG_ATTENDED, event_id)).fetchone()
    return {"event": event, "total": row["total"], "attended": row["attended"]}
