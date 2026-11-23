"""V3 этап 6: таңдаулы іс-шаралар: сервис, маршруты, UI, рөлдер."""
from app.database import get_db
from app.errors import PermissionDenied
from app.services import favorite_service
from conftest import login


def count(user_id):
    return get_db().execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)).fetchone()[0]


def test_add_and_remove_favorite(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, title="Таңдаулы іс")
    login(client, vol["email"])

    response = client.post(f"/events/{eid}/favorite", follow_redirects=True)
    assert response.status_code == 200
    assert "Іс-шара таңдаулыларға қосылды." in response.get_data(as_text=True)
    assert count(vol["id"]) == 1
    body = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "Таңдаулылардан шығару" in body

    response = client.post(f"/events/{eid}/unfavorite", follow_redirects=True)
    assert "Іс-шара таңдаулылардан шығарылды." in response.get_data(as_text=True)
    assert count(vol["id"]) == 0


def test_add_favorite_is_idempotent(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org)
    login(client, vol["email"])
    client.post(f"/events/{eid}/favorite")
    client.post(f"/events/{eid}/favorite")
    assert count(vol["id"]) == 1


def test_favorites_are_shown_on_volunteer_dashboard(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    a = make.event(org, title="Бірінші таңдаулы")
    b = make.event(org, title="Екінші таңдаулы")
    favorite_service.add(vol, a)
    favorite_service.add(vol, b)
    login(client, vol["email"])

    body = client.get("/my").get_data(as_text=True)
    assert "Менің таңдаулыларым" in body
    assert "Бірінші таңдаулы" in body and "Екінші таңдаулы" in body


def test_only_volunteers_can_favorite(client, make):
    org = make.user("organizer")
    eid = make.event(org)
    login(client, org["email"])
    assert client.post(f"/events/{eid}/favorite").status_code == 403
    assert count(org["id"]) == 0
    try:
        favorite_service.add(org, eid)
    except PermissionDenied:
        pass
    else:
        raise AssertionError("Expected PermissionDenied")


def test_service_lists_ids_and_checks_membership(ctx, make):
    org, vol, other = make.user("organizer"), make.user("volunteer"), make.user("volunteer")
    a = make.event(org)
    b = make.event(org)
    assert favorite_service.ids_for_user(vol["id"]) == set()
    favorite_service.add(vol, a)
    assert favorite_service.ids_for_user(vol["id"]) == {a}
    assert favorite_service.is_favorite(vol, a)
    assert not favorite_service.is_favorite(vol, b)
    assert not favorite_service.is_favorite(other, a)
    assert len(favorite_service.list_for_user(vol["id"])) == 1
    assert favorite_service.remove(vol, a) is True
    assert favorite_service.remove(vol, a) is False


def test_unknown_event_cannot_be_favorited(ctx, make):
    vol = make.user("volunteer")
    try:
        favorite_service.add(vol, 999999)
    except Exception as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected NotFound")
    assert count(vol["id"]) == 0
