"""Email-уведомления: языки, хуки регистрации/отмены, напоминания, отказ SMTP."""
import smtplib

from app.database import get_db
from app.services import mail_service
from conftest import login


def test_registration_mail_uses_user_language(app, client, make):
    org = make.user("organizer")
    vol = make.user("volunteer", name="Анна Тест", email="vol@mail.test")
    get_db().execute("UPDATE users SET lang='ru' WHERE id=?", (vol["id"],))
    eid = make.event(org, title="Экология Қызылорда")
    login(client, vol["email"])

    assert client.post(f"/events/{eid}/register").status_code == 302
    outbox = app.extensions["mail_outbox"]
    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["to"] == "vol@mail.test"
    assert msg["lang"] == "ru"
    assert msg["kind"] == "registration"
    assert "Регистрация на мероприятие подтверждена" in msg["subject"]
    assert "Анна Тест" in msg["body"]
    assert "Экология Қызылорда" in msg["body"]


def test_failed_registration_sends_no_mail(app, client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, capacity=1)
    make.registration(make.user("volunteer"), eid)
    login(client, vol["email"])

    client.post(f"/events/{eid}/register")
    assert app.extensions["mail_outbox"] == []


def test_cancellation_mail_is_sent(app, client, make):
    org, vol = make.user("organizer"), make.user("volunteer", email="cancel@mail.test")
    get_db().execute("UPDATE users SET lang='en' WHERE id=?", (vol["id"],))
    eid = make.event(org, title="Спорт Астана")
    rid = make.registration(vol, eid)
    login(client, vol["email"])

    assert client.post(f"/registrations/{rid}/cancel").status_code == 302
    outbox = app.extensions["mail_outbox"]
    assert len(outbox) == 1
    assert outbox[0]["kind"] == "cancellation"
    assert outbox[0]["lang"] == "en"
    assert "Registration cancelled" in outbox[0]["subject"]


def test_upcoming_reminders_only_for_near_events(app, make):
    org, vol = make.user("organizer"), make.user("volunteer", email="remind@mail.test")
    near = make.event(org, title="Ближайшее", days=2)
    far = make.event(org, title="Далекое", days=10)
    make.registration(vol, near)
    make.registration(vol, far)

    sent = mail_service.send_upcoming_reminders(days=3)
    assert sent == 1
    outbox = app.extensions["mail_outbox"]
    assert len(outbox) == 1
    assert outbox[0]["kind"] == "upcoming"
    assert "Ближайшее" in outbox[0]["subject"]


def test_smtp_failure_is_logged_but_does_not_break_flow(app, monkeypatch, make):
    vol = make.user("volunteer", email="smtp@mail.test")
    app.config["MAIL_ENABLED"] = True

    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("SMTP недоступен")

    monkeypatch.setattr(mail_service.smtplib, "SMTP", BrokenSMTP)
    mail_service.notify_registration(vol, {"id": 1, "title": "Тест", "event_date": "2026-12-01 10:00",
                                            "city": "Астана", "location": "Центр"})
    assert len(app.extensions["mail_outbox"]) == 1


def test_mail_templates_are_translated(app):
    from app.services.mail_service import SUBJECTS, BODIES
    params = dict(name="Айгүл", title="Экология", date="1 мамыр 2026", address="Қызылорда",
                  url="https://portal.test/events/1")
    for lang, marker in (("ru", "Регистрация"), ("en", "Registration")):
        subject, body = mail_service.render("registration", lang, **params)
        assert marker in subject
        assert "Айгүл" in body and "Экология" in body
        assert "{name}" not in body
    assert set(SUBJECTS) == set(BODIES)
