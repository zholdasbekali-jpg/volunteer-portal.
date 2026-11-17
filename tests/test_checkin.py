"""QR арқылы өзін-өзі белгілеу: динамикалық белгі, ережелер, рөлдер, беттер."""
from datetime import datetime, timedelta

import pytest

from app.database import transaction
from app.errors import Conflict, NotFound, PermissionDenied, ValidationError
from app.services import checkin_service as cs
from app.services.event_service import DATE_FMT

from conftest import login


def set_start(event_id, start: datetime):
    with transaction() as db:
        db.execute("UPDATE events SET event_date = ? WHERE id = ?", (start.strftime(DATE_FMT), event_id))


def live_event(make, status="pending", reg=True):
    """Іс-шара бір сағат бұрын басталған (белгілеу ашық), ерікті тіркелген."""
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org)
    set_start(eid, datetime.now() - timedelta(hours=1))
    rid = make.registration(vol, eid, status) if reg else None
    return org, vol, eid, rid


def status_of(rid):
    from app.database import get_db
    return get_db().execute("SELECT status FROM registrations WHERE id=?", (rid,)).fetchone()["status"]


def test_token_roundtrip_and_extract(ctx):
    t = cs.make_token(7, now=1000.0)
    assert cs.parse_token(t, now=1000.0) == 7
    assert cs.extract_token(f"https://site.kz/checkin/{t}?x=1") == t
    assert cs.extract_token("мәтін жоқ") is None


def test_token_expires_and_rejects_future_and_tampering(ctx):
    t = cs.make_token(7, now=1000.0)
    assert cs.parse_token(t, now=1000.0 + 60) == 7                 # ~90 с ішінде жарамды
    with pytest.raises(ValidationError):
        cs.parse_token(t, now=1000.0 + 200)                        # ескірген
    with pytest.raises(ValidationError):
        cs.parse_token(t, now=1000.0 - 200)                        # болашақтан келген
    event_id, step, sig = t.split(".")
    for bad in (f"8.{step}.{sig}", f"{event_id}.{int(step)}.{'0' * 16}", "abc", ""):
        with pytest.raises(ValidationError):
            cs.parse_token(bad, now=1000.0)


def test_check_in_marks_attended_and_is_idempotent(make):
    _, vol, eid, rid = live_event(make)
    token = cs.make_token(eid)
    assert cs.check_in(vol, token)["already"] is False
    assert status_of(rid) == "attended"
    assert cs.check_in(vol, token)["already"] is True


def test_check_in_rules(make):
    org, vol, eid, rid = live_event(make)
    token = cs.make_token(eid)
    with pytest.raises(PermissionDenied):
        cs.check_in(org, token)                                    # ұйымдастырушы өзін белгілей алмайды
    stranger = make.user("volunteer")
    with pytest.raises(Conflict):
        cs.check_in(stranger, token)                               # тіркелмеген
    set_start(eid, datetime.now() + timedelta(hours=5))
    with pytest.raises(Conflict):
        cs.check_in(vol, token)                                    # әлі ерте
    set_start(eid, datetime.now() - timedelta(hours=30))
    with pytest.raises(Conflict):
        cs.check_in(vol, token)                                    # уақыты өтіп кеткен
    assert status_of(rid) == "pending"
    set_start(eid, datetime.now() - timedelta(hours=1))
    with transaction() as db:
        db.execute("UPDATE events SET status='cancelled' WHERE id=?", (eid,))
    with pytest.raises(Conflict):
        cs.check_in(vol, token)                                    # тоқтатылған іс-шара
    with pytest.raises(ValidationError):
        cs.check_in(vol, "1.2.3")


def test_other_events_token_does_not_mark_this_event(make):
    _, vol, eid, rid = live_event(make)
    org2 = make.user("organizer")
    other = make.event(org2)
    set_start(other, datetime.now() - timedelta(hours=1))
    with pytest.raises(Conflict):
        cs.check_in(vol, cs.make_token(other))                     # тіркелмеген іс-шараның белгісі
    assert status_of(rid) == "pending"


def test_attendance_counts_permissions(make):
    org, vol, eid, _ = live_event(make, status="attended")
    other_org = make.user("organizer")
    assert cs.attendance_counts(org, eid)["attended"] == 1
    with pytest.raises(PermissionDenied):
        cs.attendance_counts(other_org, eid)
    with pytest.raises(NotFound):
        cs.attendance_counts(org, 9999)


def test_http_flow_organizer_screen_and_volunteer_confirm(client, make):
    org, vol, eid, rid = live_event(make)
    # ұйымдастырушы экраны
    login(client, org["email"])
    assert client.get(f"/organizer/events/{eid}/checkin").status_code == 200
    svg = client.get(f"/organizer/events/{eid}/checkin/qr.svg")
    assert svg.status_code == 200 and svg.mimetype == "image/svg+xml" and b"<svg" in svg.data
    assert svg.headers["Cache-Control"] == "no-store"
    stats = client.get(f"/organizer/events/{eid}/checkin/stats").get_json()
    assert stats == {"total": 1, "attended": 0}
    client.post("/logout")
    # ерікті: сканер арқылы белгі келеді, GET дерек өзгертпейді, POST белгілейді
    token = cs.make_token(eid)
    login(client, vol["email"])
    r = client.get("/verify", query_string={"code": f"http://localhost/checkin/{token}"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/checkin/{token}")
    page = client.get(f"/checkin/{token}")
    assert page.status_code == 200 and "Мен осындамын" in page.get_data(as_text=True)
    assert status_of(rid) == "pending"
    assert client.post(f"/checkin/{token}", follow_redirects=True).status_code == 200
    assert status_of(rid) == "attended"
    client.post("/logout")
    login(client, org["email"])
    assert client.get(f"/organizer/events/{eid}/checkin/stats").get_json()["attended"] == 1


def test_http_permissions_and_bad_tokens(client, make):
    org, vol, eid, _ = live_event(make)
    other = make.user("organizer")
    assert client.get(f"/organizer/events/{eid}/checkin").status_code in (302, 401)
    assert client.get(f"/checkin/{cs.make_token(eid)}").status_code == 302       # кіру бетіне
    login(client, vol["email"])
    assert client.get(f"/organizer/events/{eid}/checkin").status_code == 403     # ерікті экранды көре алмайды
    old = cs.make_token(eid, now=1000.0)
    r = client.get(f"/checkin/{old}")
    assert r.status_code == 400 and "ескірген" in r.get_data(as_text=True)
    client.post("/logout")
    login(client, other["email"])
    assert client.get(f"/organizer/events/{eid}/checkin/qr.svg").status_code == 403
    assert client.get(f"/checkin/{cs.make_token(eid)}").status_code == 403       # ұйымдастырушы ерікті емес
    client.post("/logout")
    login(client, org["email"])
    assert client.get("/organizer/events/9999/checkin").status_code == 404


def test_qr_uses_public_url(app, client, make):
    app.config["PUBLIC_URL"] = "https://portal.example.kz"
    org, _, eid, _ = live_event(make)
    login(client, org["email"])
    from app.checkin import _qr_svg
    assert _qr_svg("https://portal.example.kz/checkin/1.2.abc").startswith("<?xml")
    assert client.get(f"/organizer/events/{eid}/checkin/qr.svg").status_code == 200


def test_participants_page_links_to_qr_screen(client, make):
    org, _, eid, _ = live_event(make)
    login(client, org["email"])
    assert f"/organizer/events/{eid}/checkin" in client.get(f"/organizer/events/{eid}/participants").get_data(as_text=True)
