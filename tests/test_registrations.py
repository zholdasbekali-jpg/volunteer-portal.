"""FR-04, FR-05, NFR-03: тіркелу, орын саны, қайталануды болдырмау, транзакциялар, қатысуды бақылау."""
import threading

import pytest

from app import create_app
from app.database import get_db, transaction
from app.errors import Conflict, NotFound, PermissionDenied, ValidationError
from app.services import registration_service as rs
from config import TestConfig
from conftest import login


def test_register_success(ctx, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, capacity=2)
    rid = rs.register(vol, eid)
    assert rs.get_user_registration(vol["id"], eid)["id"] == rid
    assert rs.list_for_user(vol["id"])[0]["status"] == "pending"


def test_register_rejected_when_full(ctx, make):
    org = make.user("organizer")
    eid = make.event(org, capacity=2)
    rs.register(make.user(), eid)
    rs.register(make.user(), eid)
    with pytest.raises(Conflict, match="Бос орын қалмады"):
        rs.register(make.user(), eid)


def test_duplicate_registration_forbidden(ctx, make):
    vol = make.user()
    eid = make.event(make.user("organizer"))
    rs.register(vol, eid)
    with pytest.raises(Conflict, match="бұрын тіркелгенсіз"):
        rs.register(vol, eid)
    count = get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    assert count == 1


def test_db_unique_constraint_blocks_duplicates(ctx, make):
    """Бизнес-логикадан бөлек, деректер қорының өзі UNIQUE(user_id, event_id) арқылы қорғайды."""
    import sqlite3
    vol = make.user()
    eid = make.event(make.user("organizer"))
    make.registration(vol, eid)
    with pytest.raises(sqlite3.IntegrityError):
        make.registration(vol, eid)


def test_cancel_registration_frees_spot(ctx, make):
    org, v1, v2 = make.user("organizer"), make.user(), make.user()
    eid = make.event(org, capacity=1)
    rid = rs.register(v1, eid)
    with pytest.raises(Conflict):
        rs.register(v2, eid)
    rs.cancel_registration(v1, rid)          # орын қайта босады
    rs.register(v2, eid)
    from app.services import event_service
    assert event_service.get_event(eid)["registered_count"] == 1


def test_cancel_only_own_registration(ctx, make):
    v1, v2 = make.user(), make.user()
    eid = make.event(make.user("organizer"))
    rid = rs.register(v1, eid)
    with pytest.raises(PermissionDenied):
        rs.cancel_registration(v2, rid)
    with pytest.raises(NotFound):
        rs.cancel_registration(v1, 9999)


def test_cannot_register_for_cancelled_or_past_event(ctx, make):
    org, vol = make.user("organizer"), make.user()
    with pytest.raises(Conflict, match="тоқтатылған"):
        rs.register(vol, make.event(org, status="cancelled"))
    with pytest.raises(Conflict, match="өтіп кеткен"):
        rs.register(vol, make.event(org, days=-1))
    with pytest.raises(NotFound):
        rs.register(vol, 12345)


def test_only_volunteer_can_register(ctx, make):
    org = make.user("organizer")
    eid = make.event(org)
    with pytest.raises(PermissionDenied):
        rs.register(org, eid)
    with pytest.raises(PermissionDenied):
        rs.register(None, eid)


def test_failed_transaction_rolls_back(ctx, make):
    """Транзакция ішінде қате болса, барлық өзгеріс қайтарылады."""
    vol = make.user()
    eid = make.event(make.user("organizer"))
    with pytest.raises(RuntimeError):
        with transaction() as db:
            db.execute("INSERT INTO registrations (user_id, event_id) VALUES (?, ?)", (vol["id"], eid))
            raise RuntimeError("қате")
    assert get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 0


def test_concurrent_registration_never_exceeds_capacity(app, make):
    """5 ерікті бір мезгілде 2 орынға тіркеледі: нақты 2 сәтті болуы керек (race condition жоқ)."""
    org = make.user("organizer")
    eid = make.event(org, capacity=2)
    vols = [make.user() for _ in range(5)]
    results = []

    def worker(v):
        with app.app_context():
            try:
                rs.register(v, eid)
                results.append("ok")
            except Conflict:
                results.append("full")

    threads = [threading.Thread(target=worker, args=(v,)) for v in vols]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 2 and results.count("full") == 3
    assert get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 2


def test_set_attendance_statuses_persist(ctx, make):
    org, vol = make.user("organizer"), make.user()
    eid = make.event(org, days=-1)
    rid = make.registration(vol, eid)
    for status in ("attended", "absent", "pending"):
        rs.set_attendance(org, rid, status)
        assert get_db().execute("SELECT status FROM registrations WHERE id=?", (rid,)).fetchone()[0] == status
    with pytest.raises(ValidationError):
        rs.set_attendance(org, rid, "unknown")


def test_set_attendance_only_by_event_owner(ctx, make):
    org, other, vol = make.user("organizer"), make.user("organizer"), make.user()
    rid = make.registration(vol, make.event(org))
    with pytest.raises(PermissionDenied):
        rs.set_attendance(other, rid, "attended")
    with pytest.raises(PermissionDenied):
        rs.set_attendance(vol, rid, "attended")
    with pytest.raises(PermissionDenied):
        rs.list_for_event(other, get_db().execute("SELECT event_id FROM registrations").fetchone()[0])
    with pytest.raises(NotFound):
        rs.set_attendance(org, 777, "attended")


def test_list_all_admin_only(ctx, make):
    adm, vol = make.user("admin"), make.user()
    make.registration(vol, make.event(make.user("organizer")))
    assert len(rs.list_all(adm)) == 1
    with pytest.raises(PermissionDenied):
        rs.list_all(vol)


def test_http_register_and_cancel_flow(client, make):
    org, vol = make.user("organizer"), make.user()
    eid = make.event(org, capacity=1)
    login(client, vol["email"])
    r = client.post(f"/events/{eid}/register", follow_redirects=True)
    assert "сәтті тіркелдіңіз" in r.get_data(as_text=True)
    r = client.post(f"/events/{eid}/register", follow_redirects=True)
    assert "бұрын тіркелгенсіз" in r.get_data(as_text=True)
    rid = rs.get_user_registration(vol["id"], eid)["id"]
    r = client.post(f"/registrations/{rid}/cancel", follow_redirects=True)
    assert "орын босатылды" in r.get_data(as_text=True)


def test_http_organizer_marks_attendance_and_other_gets_403(client, make):
    org, other, vol = make.user("organizer"), make.user("organizer"), make.user()
    eid = make.event(org)
    rid = make.registration(vol, eid)
    login(client, other["email"])
    assert client.post(f"/registrations/{rid}/status", data={"status": "attended", "event_id": eid}).status_code == 403
    client.post("/logout")
    login(client, org["email"])
    r = client.post(f"/registrations/{rid}/status", data={"status": "attended", "event_id": eid}, follow_redirects=True)
    assert "жаңартылды" in r.get_data(as_text=True)
    assert "Қатысты" in client.get(f"/organizer/events/{eid}/participants").get_data(as_text=True)


def test_data_persists_after_restart(tmp_path):
    """NFR-03: қосымша қайта іске қосылғаннан кейін деректер сақталады."""
    db_path, cert_dir = str(tmp_path / "persist.db"), str(tmp_path / "c")
    app1 = create_app(TestConfig, DATABASE=db_path, CERTIFICATE_DIR=cert_dir)
    with app1.app_context():
        from conftest import Factory
        f = Factory()
        org, vol = f.user("organizer"), f.user()
        eid = f.event(org, title="Тұрақты іс-шара")
        rs.register(vol, eid)
    app2 = create_app(TestConfig, DATABASE=db_path, CERTIFICATE_DIR=cert_dir)   # «қайта іске қосу»
    with app2.app_context():
        assert get_db().execute("SELECT title FROM events").fetchone()[0] == "Тұрақты іс-шара"
        assert get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 1
