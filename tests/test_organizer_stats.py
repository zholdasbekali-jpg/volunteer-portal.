"""V3 этап 8: кеңейтілген ұйымдастырушы статистикасы.

Бар get_summary/get_event_stats өзгермейді: жаңа көрсеткіштер бөлек get_extended-те.
Қамтылады: қатысу %, күту тізімі, пікірлер/орташа баға, алдағы/өткен іс-шаралар,
санаттар бойынша бөлініс, санат диаграммасы, статистика бетіндегі UI, рөлдер.
"""
import pytest

from app.database import get_db, transaction
from app.errors import NotFound
from app.services import statistics_service as ss
from conftest import login, when


def set_category(eid, code):
    with transaction() as db:
        db.execute("UPDATE events SET category=? WHERE id=?", (code, eid))


def add_waitlist(uid, eid):
    with transaction() as db:
        db.execute("INSERT OR IGNORE INTO waitlist (user_id, event_id) VALUES (?,?)", (uid, eid))


def add_review(uid, eid, rating):
    with transaction() as db:
        db.execute("INSERT OR IGNORE INTO reviews (user_id, event_id, rating, comment) VALUES (?,?,?,?)",
                   (uid, eid, rating, "пікір"))


def populate_extended(make):
    org1, org2 = make.user("organizer"), make.user("organizer")
    v1, v2, v3 = make.user(), make.user(), make.user()
    e1 = make.event(org1, capacity=2, days=-3)
    e2 = make.event(org1, capacity=4, days=4)
    e3 = make.event(org1, capacity=10, days=6)
    e4 = make.event(org2, capacity=5, days=2)
    set_category(e1, "ecology")
    set_category(e2, "education")
    set_category(e3, "ecology")
    set_category(e4, "sport")

    make.registration(v1, e1, "attended")
    make.registration(v2, e1, "absent")
    make.registration(v1, e2)
    make.registration(v2, e2)
    make.registration(v3, e3, "attended")
    make.registration(v1, e4)  # басқа ұйымдастырушының тіркелімі

    add_waitlist(v1["id"], e2)
    add_waitlist(v2["id"], e2)
    add_waitlist(v3["id"], e3)
    add_waitlist(v1["id"], e4)  # есепке кірмеуі керек

    add_review(v1["id"], e1, 5)
    add_review(v2["id"], e1, 3)
    add_review(v3["id"], e3, 4)
    add_review(v1["id"], e4, 1)  # есепке кірмеуі керек
    return org1, org2, (e1, e2, e3, e4)


def test_extended_scoped_to_organizer(ctx, make):
    org1, _, _ = populate_extended(make)
    x = ss.get_extended(org1["id"])
    assert x["attendance_rate"] == 40.0           # 2 attended / 5 registrations
    assert x["waitlist_total"] == 3                # тек org1 іс-шараларындағы кезек
    assert x["reviews_total"] == 3
    assert x["avg_rating"] == 4.0                  # (5+3+4)/3
    assert x["upcoming_total"] == 2                # e2, e3
    assert x["past_total"] == 1                    # e1


def test_extended_by_category(ctx, make):
    org1, _, _ = populate_extended(make)
    by = ss.get_extended(org1["id"])["by_category"]
    rows = {r["code"]: r for r in by}
    assert set(rows) == {"ecology", "education"}
    assert rows["ecology"]["events"] == 2 and rows["ecology"]["registrations"] == 3
    assert rows["education"]["events"] == 1 and rows["education"]["registrations"] == 2
    assert rows["ecology"]["label"] == "Экология"
    # тіркелім саны азаю ретімен сұрыпталады
    assert [r["code"] for r in by] == ["ecology", "education"]


def test_extended_platform_scope(ctx, make):
    populate_extended(make)
    x = ss.get_extended()
    assert x["waitlist_total"] == 4 and x["reviews_total"] == 4
    assert x["attendance_rate"] == round(2 * 100 / 6, 1)  # 2/6 тіркелім


def test_extended_empty_database(ctx):
    x = ss.get_extended()
    assert x["attendance_rate"] == 0.0
    assert x["waitlist_total"] == 0 and x["reviews_total"] == 0
    assert x["avg_rating"] is None
    assert x["upcoming_total"] == 0 and x["past_total"] == 0
    assert x["by_category"] == []


def test_category_chart_added_and_png(ctx, make):
    assert "category" in ss.CHART_NAMES
    populate_extended(make)
    assert ss.render_chart("category").startswith(b"\x89PNG")
    assert ss.render_chart("category", 999999).startswith(b"\x89PNG")  # бос жиын


def test_statistics_page_shows_extended_metrics(client, make):
    org1, _, _ = populate_extended(make)
    login(client, org1["email"])
    body = client.get("/statistics").get_data(as_text=True)
    assert "Кеңейтілген көрсеткіштер" in body
    assert "Қатысу пайызы" in body and "Орташа баға" in body
    assert "/statistics/chart/category.png" in body
    assert "Экология" in body and "category" in body
    assert client.get("/statistics/chart/category.png").status_code == 200


def test_organizer_cannot_see_other_organizer_extended(client, ctx, make):
    org1, org2, _ = populate_extended(make)
    x1 = ss.get_extended(org1["id"])
    x2 = ss.get_extended(org2["id"])
    assert x1["waitlist_total"] == 3 and x2["waitlist_total"] == 1
    assert x1["reviews_total"] == 3 and x2["reviews_total"] == 1


def test_unknown_chart_still_rejected(ctx):
    with pytest.raises(NotFound):
        ss.render_chart("category/../../etc")
