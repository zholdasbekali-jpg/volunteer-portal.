"""Күту тізімі: қосылу, шығу, FIFO повышение, хабарлама және қолжетімділік."""
from app.database import get_db
from app.errors import ServiceError
from app.services import mail_service, waitlist_service
from conftest import login


def _registered(user_id, event_id):
    return get_db().execute("SELECT id FROM registrations WHERE user_id=? AND event_id=?",
                            (user_id, event_id)).fetchone()


def _waiting(user_id, event_id):
    return get_db().execute("SELECT id FROM waitlist WHERE user_id=? AND event_id=?",
                            (user_id, event_id)).fetchone()


def test_join_waitlist_when_full(app, client, make):
    org, v1, v2 = make.user("organizer"), make.user("volunteer"), make.user("volunteer")
    eid = make.event(org, capacity=1)
    make.registration(v1, eid)
    login(client, v2["email"])

    response = client.post(f"/events/{eid}/waitlist/join", follow_redirects=True)
    assert response.status_code == 200
    assert "Сіз күту тізіміне қосылдыңыз" in response.get_data(as_text=True)
    assert _waiting(v2["id"], eid) is not None
    assert waitlist_service.position(v2["id"], eid) == 1
    body = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "Күту тізіміндегі орныңыз" in body


def test_cancel_promotes_first_in_queue_and_notifies(app, client, make):
    org, v1, v2, v3 = (make.user("organizer"), make.user("volunteer", email="v1@mail.test"),
                       make.user("volunteer", email="v2@mail.test"), make.user("volunteer"))
    eid = make.event(org, capacity=1, title="Экология")
    r1 = make.registration(v1, eid)
    waitlist_service.join(v2, eid)
    waitlist_service.join(v3, eid)
    assert [r["user_id"] for r in waitlist_service.list_for_event(org, eid)] == [v2["id"], v3["id"]]
    login(client, v1["email"])

    assert client.post(f"/registrations/{r1}/cancel").status_code == 302
    assert _registered(v2["id"], eid) is not None          # бірінші кіші қатысушыға орын берілді
    assert _registered(v3["id"], eid) is None
    assert _waiting(v2["id"], eid) is None                 # қатардан шығарылды
    assert waitlist_service.position(v3["id"], eid) == 1   # енді бірінші
    promoted = [m for m in app.extensions["mail_outbox"] if m["kind"] == "promotion"]
    assert len(promoted) == 1 and promoted[0]["to"] == "v2@mail.test"


def test_leave_waitlist(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, capacity=1)
    make.registration(make.user("volunteer"), eid)
    login(client, vol["email"])
    client.post(f"/events/{eid}/waitlist/join")

    response = client.post(f"/events/{eid}/waitlist/leave", follow_redirects=True)
    assert "Сіз күту тізімінен шықтыңыз" in response.get_data(as_text=True)
    assert _waiting(vol["id"], eid) is None


def test_join_rejects_invalid_states(ctx, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    free = make.event(org, capacity=5)
    full = make.event(org, capacity=1)
    make.registration(vol, full)
    past = make.event(org, capacity=1, days=-2)
    cancelled = make.event(org, capacity=1, status="cancelled")

    for eid in (free, full, past, cancelled):
        try:
            waitlist_service.join(vol, eid)
        except ServiceError:
            pass
        else:
            raise AssertionError(f"Expected ServiceError for event {eid}")
    assert get_db().execute("SELECT COUNT(*) FROM waitlist").fetchone()[0] == 0


def test_organizer_sees_waitlist_on_participants_page(client, make):
    org, v1, v2 = make.user("organizer"), make.user("volunteer"), make.user("volunteer", name="Күтуші Ерікті")
    eid = make.event(org, capacity=1)
    make.registration(v1, eid)
    waitlist_service.join(v2, eid)
    login(client, org["email"])

    body = client.get(f"/organizer/events/{eid}/participants").get_data(as_text=True)
    assert "Күту тізімі" in body and "Күтуші Ерікті" in body


def test_promotion_never_exceeds_capacity(ctx, make):
    org, v1, v2 = make.user("organizer"), make.user("volunteer"), make.user("volunteer")
    eid = make.event(org, capacity=1)
    r1 = make.registration(v1, eid)
    waitlist_service.join(v2, eid)
    # Екі рет қатарынан шақырсақ та бір ғана адам өтеді (капацитеттен аспайды)
    from app.services import registration_service
    registration_service.cancel_registration(v1, r1)
    assert get_db().execute("SELECT COUNT(*) FROM registrations WHERE event_id=?", (eid,)).fetchone()[0] == 1
    assert _waiting(v2["id"], eid) is None
