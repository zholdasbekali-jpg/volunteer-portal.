"""V3: email-уведомления (регистрация, отмена, напоминания, лист ожидания).

Переводы живут в обычных каталогах ru.json/en.json: ключ — казахский текст шаблона.
По умолчанию письма попадают в outbox в памяти (реальная отправка включается MAIL_ENABLED=1),
поэтому тесты и локальная разработка не обращаются к внешнему SMTP.
"""
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import current_app, has_request_context, request

from .. import i18n
from ..database import get_db
from . import auth_service, event_service

SUBJECTS = {
    "registration": "Іс-шараға тіркелу расталды: {title}",
    "cancellation": "Іс-шараға тіркелуден бас тартылды: {title}",
    "upcoming": "Жақын арада өтетін іс-шара: {title}",
    "waitlist": "Күту тізіміне қосылдыңыз: {title}",
    "promotion": "Күту тізімінен іс-шараға қабылдандыңыз: {title}",
    "approval": "Ұйымдастырушы ретіндегі тіркелуіңіз мақұлданды",
}

BODIES = {
    "registration": "{name}, сіз «{title}» іс-шарасына тіркелдіңіз. Күні: {date}. Мекенжайы: {address}. Сілтеме: {url}",
    "cancellation": "{name}, сіз «{title}» іс-шарасындағы тіркелуіңізден бас тарттыңыз. Сілтеме: {url}",
    "upcoming": "{name}, «{title}» іс-шарасы жақын арада өтеді. Күні: {date}. Мекенжайы: {address}. Сілтеме: {url}",
    "waitlist": "{name}, «{title}» іс-шарасында бос орын қалмағандықтан сіз күту тізіміне қосылдыңыз. Орын босағанда міндетті түрде хабарлаймыз. Сілтеме: {url}",
    "promotion": "{name}, «{title}» іс-шарасында орын босап, сіз қатысушы ретінде тіркелдіңіз. Күні: {date}. Сілтеме: {url}",
    "approval": "{name}, сіздің ұйымдастырушы ретіндегі тіркелуіңіз мақұлданды. Енді өз іс-шараларыңызды құра аласыз. Сілтеме: {url}",
}


def init_app(app) -> None:
    """Создаёт outbox уровня приложения (для тестов и режима без SMTP)."""
    app.extensions["mail_outbox"] = []


def outbox() -> list:
    return current_app.extensions.setdefault("mail_outbox", [])


def render(kind: str, lang: str, **params) -> tuple[str, str]:
    """Возвращает переведённые тему и текст письма."""
    if kind not in SUBJECTS:
        raise ValueError(f"Unknown notification kind: {kind}")
    return (i18n.translate(SUBJECTS[kind], lang=lang, **params),
            i18n.translate(BODIES[kind], lang=lang, **params))


def _base_url() -> str:
    configured = (current_app.config.get("PUBLIC_URL") or "").rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/") if has_request_context() else "http://localhost"


def _get(row, key, default=None):
    """Работает и со sqlite3.Row/dict, и с flask_login User (у которого есть __getitem__)."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _user_lang(user) -> str:
    """Язык пользователя из профиля; для User без поля lang — язык по умолчанию."""
    uid = _get(user, "id")
    if uid:
        row = auth_service.get_user(uid)
        if row and row["lang"] in i18n.CODES:
            return row["lang"]
    return i18n.DEFAULT_LANG


def send(to: str, subject: str, body: str, *, kind: str = "", lang: str = "") -> bool:
    """Кладет письмо в outbox и, если включено, отправляет через SMTP.

    Сбой SMTP не должен ломать пользовательский сценарий: ошибка логируется,
    письмо остаётся в outbox (при включённом MAIL_ENABLED его можно доставить повторно).
    """
    outbox().append({"to": to, "subject": subject, "body": body, "kind": kind, "lang": lang})
    if not current_app.config.get("MAIL_ENABLED"):
        return True
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["MAIL_DEFAULT_SENDER"]
    message["To"] = to
    message.set_content(body)
    try:
        with smtplib.SMTP(current_app.config["MAIL_SERVER"],
                          current_app.config["MAIL_PORT"], timeout=10) as smtp:
            if current_app.config.get("MAIL_USE_TLS"):
                smtp.starttls()
            username = current_app.config.get("MAIL_USERNAME")
            if username:
                smtp.login(username, current_app.config.get("MAIL_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        current_app.logger.warning("Хат жіберілмеді (%s): %s", to, exc)
    return True


def notify(user, event, kind: str, **extra) -> bool:
    """Формирует письмо по типу события и языке пользователя."""
    if user is None or not _get(user, "email"):
        return False
    lang = _user_lang(user)
    params = {
        "name": _get(user, "full_name", ""),
        "title": event["title"] if event else "",
        "date": i18n.format_date(event["event_date"], lang=lang) if event else "",
        "address": event_service.full_address(event, lang=lang) if event else "",
        "url": f"{_base_url()}/events/{event['id']}" if event else _base_url(),
    }
    params.update(extra)
    subject, body = render(kind, lang, **params)
    return send(_get(user, "email"), subject, body, kind=kind, lang=lang)


def notify_registration(user, event) -> bool:
    return notify(user, event, "registration")


def notify_cancellation(user, event) -> bool:
    return notify(user, event, "cancellation")


def notify_upcoming(user, event) -> bool:
    return notify(user, event, "upcoming")


def notify_waitlist(user, event) -> bool:
    return notify(user, event, "waitlist")


def notify_promotion(user, event) -> bool:
    return notify(user, event, "promotion")


def notify_approval(user) -> bool:
    return notify(user, None, "approval", url=f"{_base_url()}/organizer")


def send_upcoming_reminders(days: int | None = None) -> int:
    """Рассылает напоминания за N дней до события всем зарегистрированным волонтёрам."""
    if days is None:
        days = current_app.config.get("MAIL_REMINDER_DAYS", 3)
    now = datetime.now()
    until = now + timedelta(days=int(days))
    rows = get_db().execute(
        """SELECT r.user_id, r.event_id FROM registrations r
           JOIN events e ON e.id = r.event_id
           WHERE e.status = 'published' AND e.event_date > ? AND e.event_date <= ?
           ORDER BY e.event_date, r.user_id""",
        (now.strftime(event_service.DATE_FMT), until.strftime(event_service.DATE_FMT))).fetchall()
    users, events, sent = {}, {}, 0
    for row in rows:
        uid, eid = row["user_id"], row["event_id"]
        if uid not in users:
            users[uid] = auth_service.get_user(uid)
        if eid not in events:
            events[eid] = event_service.get_event(eid)
        if notify(users[uid], events[eid], "upcoming"):
            sent += 1
    return sent
