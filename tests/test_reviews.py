"""V3 этап 4: отзывы и оценки после события (проверки, защита, вывод, безопасность)."""
import pytest

from app.database import get_db
from app.models import REG_ATTENDED
from app.services import review_service
from conftest import login


def attended(make, vol, eid):
    make.registration(vol, eid, status=REG_ATTENDED)


def post_review(client, eid, rating=5, comment="Очень хорошее мероприятие"):
    return client.post(f"/events/{eid}/reviews", data={"rating": str(rating), "comment": comment},
                       follow_redirects=True)


def test_volunteer_can_review_past_attended_event(app, client, make):
    org, vol = make.user("organizer"), make.user("volunteer", name="Анна Отзыв")
    eid = make.event(org, title="Экология", days=-2)
    attended(make, vol, eid)
    login(client, vol["email"])

    response = post_review(client, eid, rating=5, comment="Отличная экология")
    assert response.status_code == 200
    assert "Пікіріңіз сақталды" in response.get_data(as_text=True)
    row = get_db().execute("SELECT * FROM reviews WHERE event_id=?", (eid,)).fetchone()
    assert row["user_id"] == vol["id"] and row["rating"] == 5
    assert row["comment"] == "Отличная экология"
    text = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "Отличная экология" in text and "Анна Отзыв" in text


def test_review_requires_attended_registration(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, days=-2)
    make.registration(vol, eid)  # pending
    login(client, vol["email"])

    assert post_review(client, eid).status_code == 403
    assert get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_review_requires_past_event(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, days=5)
    attended(make, vol, eid)
    login(client, vol["email"])

    assert post_review(client, eid).status_code == 403
    assert get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


@pytest.mark.parametrize("rating", ["0", "6", "abc", "", "3.5"])
def test_invalid_rating_is_rejected(client, make, rating):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, days=-2)
    attended(make, vol, eid)
    login(client, vol["email"])

    response = post_review(client, eid, rating=rating)
    assert response.status_code == 200
    assert "Баға 1 мен 5 арасында болуы керек." in response.get_data(as_text=True)
    assert get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_too_long_comment_is_rejected(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, days=-2)
    attended(make, vol, eid)
    login(client, vol["email"])

    response = post_review(client, eid, comment="x" * 2001)
    assert "Пікір 2000 таңбадан аспауы керек." in response.get_data(as_text=True)
    assert get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_duplicate_review_is_rejected(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, days=-2)
    attended(make, vol, eid)
    login(client, vol["email"])
    post_review(client, eid)

    response = post_review(client, eid, comment="Екінші пікір")
    assert "Сіз бұл іс-шараға пікір қалдырғансыз." in response.get_data(as_text=True)
    assert get_db().execute("SELECT COUNT(*) FROM reviews WHERE event_id=?", (eid,)).fetchone()[0] == 1


def test_average_and_reviews_shown_with_private_name(make, client):
    org = make.user("organizer")
    v1 = make.user("volunteer", name="Көрінетін Ерікті")
    v2 = make.user("volunteer", name="Жасырын Ерікті")
    get_db().execute("UPDATE users SET id_public=0 WHERE id=?", (v2["id"],))
    eid = make.event(org, days=-2)
    attended(make, v1, eid)
    attended(make, v2, eid)
    review_service.add(v1, eid, 5, "Бірінші пікір")
    review_service.add(v2, eid, 4, "Екінші пікір")

    body = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "Орташа баға" in body and "4.5" in body
    assert "Бірінші пікір" in body and "Екінші пікір" in body
    assert "Көрінетін Ерікті" in body and "Жасырын ерікті" in body
    assert "Жасырын Ерікті" not in body


def test_review_sums_do_not_leak_html(make, client):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org, days=-2)
    attended(make, vol, eid)
    review_service.add(vol, eid, 3, "<script>alert(1)</script>")

    body = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_anonymous_cannot_review(client, make):
    org = make.user("organizer")
    eid = make.event(org, days=-2)
    response = client.post(f"/events/{eid}/reviews", data={"rating": "5", "comment": "х"})
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    assert get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_can_review_flag_and_summary(ctx, make):
    org = make.user("organizer")
    ok, no_reg, future = (make.user("volunteer"), make.user("volunteer"), make.user("volunteer"))
    past = make.event(org, days=-2)
    upcoming = make.event(org, days=5)
    attended(make, ok, past)
    attended(make, future, upcoming)

    assert review_service.can_review(ok, past)
    assert not review_service.can_review(no_reg, past)
    assert not review_service.can_review(future, upcoming)
    assert review_service.summary(past) == {"count": 0, "average": None}
    review_service.add(ok, past, 3, "Пікір")
    assert review_service.summary(past) == {"count": 1, "average": 3.0}
    assert not review_service.can_review(ok, past)  # бір рет қана
