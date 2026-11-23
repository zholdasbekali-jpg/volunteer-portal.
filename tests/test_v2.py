"""V2: Volunteer ID, жетістіктер, рейтинг, ақылды іздеу, іс-шара сағаты."""
from datetime import date

import pytest

from app.errors import NotFound, ValidationError
from app.services import event_service, rating_service as rs, search_service, volunteer_service as vs
from app.database import get_db
from conftest import login, when


def _attend(make, vol, org, n, hours=3, city="Қызылорда"):
    for i in range(n):
        eid = make.event(org, days=-2 - i, hours=hours, city=city)
        make.registration(vol, eid, "attended")


# ---------- Volunteer ID ----------
def test_every_user_gets_unique_code(make):
    codes = {get_db().execute("SELECT public_code FROM users WHERE id=?", (make.user()["id"],)).fetchone()[0]
             for _ in range(5)}
    assert len(codes) == 5 and all(c.startswith("VID-") and len(c) == 12 for c in codes)


def test_stats_count_only_attended_hours(make):
    org, vol = make.user("organizer"), make.user()
    make.registration(vol, make.event(org, days=-1, hours=4), "attended")
    make.registration(vol, make.event(org, days=-2, hours=2), "attended")
    make.registration(vol, make.event(org, days=-3, hours=9), "absent")
    make.registration(vol, make.event(org, days=3, hours=9), "pending")
    assert vs.stats_for(get_db(), vol["id"]) == {"events": 2, "hours": 6, "cities": 1}


def test_achievements_and_levels(make):
    org, vol = make.user("organizer"), make.user()
    assert not any(a["earned"] for a in vs.achievements_for(vs.stats_for(get_db(), vol["id"])))
    _attend(make, vol, org, 3, hours=4, city="Астана")
    card = vs.get_own_card(vol)
    earned = {a["key"] for a in card["achievements"] if a["earned"]}
    assert earned == {"first", "active", "h10"} and card["level"] == "Тәжірибелі"
    assert vs.level_for(0) == "Жаңа" and vs.level_for(10) == "Эксперт"


def test_traveler_needs_three_cities(make):
    org, vol = make.user("organizer"), make.user()
    for c in ("Астана", "Алматы", "Шымкент"):
        make.registration(vol, make.event(org, days=-2, city=c), "attended")
    assert "traveler" in {a["key"] for a in vs.get_own_card(vol)["achievements"] if a["earned"]}


def test_public_card_page_and_privacy(client, make):
    org, vol = make.user("organizer"), make.user(name="Айдос Серіков")
    _attend(make, vol, org, 1)
    code = vs.get_own_card(vol)["code"]
    page = client.get(f"/id/{code}").get_data(as_text=True)
    assert "Айдос Серіков" in page and code in page
    assert client.get(f"/id/{code}/qr.svg").mimetype == "image/svg+xml"
    login(client, vol["email"])
    client.post("/cabinet/id/visibility", data={"public": "0"})
    assert vs.get_public_card(code) == {"private": True, "code": code}
    hidden = client.get(f"/id/{code}").get_data(as_text=True)
    assert "Профиль жабық" in hidden and "Жетістіктер" not in hidden


def test_unknown_and_organizer_codes_give_404(client, make):
    org = make.user("organizer")
    code = get_db().execute("SELECT public_code FROM users WHERE id=?", (org["id"],)).fetchone()[0]
    assert client.get("/id/VID-NOPE1234").status_code == 404
    assert client.get(f"/id/{code}").status_code == 404      # ұйымдастырушыға ID берілмейді
    with pytest.raises(NotFound):
        vs.get_public_card("")


def test_own_card_access_rules(client, make):
    assert client.get("/cabinet/id").status_code == 302
    org = make.user("organizer")
    login(client, org["email"])
    r = client.get("/cabinet/id")
    assert r.status_code == 302 and "/cabinet/" in r.headers["Location"]
    assert client.post("/cabinet/id/visibility", data={"public": "0"}).status_code == 403


def test_visibility_requires_csrf(app, make):
    app.config["CSRF_ENABLED"] = True
    vol = make.user()
    c = app.test_client()
    login(c, vol["email"])
    assert c.post("/cabinet/id/visibility", data={"public": "0"}).status_code == 400
    row = get_db().execute("SELECT id_public FROM users WHERE id=?", (vol["id"],)).fetchone()
    assert row["id_public"] == 1


def test_volunteer_sees_id_in_cabinet(client, make):
    vol = make.user()
    login(client, vol["email"])
    assert "/cabinet/id" in client.get("/cabinet/").get_data(as_text=True)
    page = client.get("/cabinet/id").get_data(as_text=True)
    assert "Volunteer ID" in page and "Жариялылық" in page


# ---------- Рейтинг ----------
def test_rating_orders_by_hours_then_events(client, make):
    org = make.user("organizer")
    a, b, c = make.user(name="Бірінші"), make.user(name="Екінші"), make.user(name="Үшінші")
    _attend(make, a, org, 2, hours=5)    # 10 сағ
    _attend(make, b, org, 3, hours=4)    # 12 сағ
    _attend(make, c, org, 1, hours=10)   # 10 сағ, 1 іс-шара
    top = rs.top_volunteers()
    assert [v["name"] for v in top] == ["Екінші", "Бірінші", "Үшінші"]
    assert top[0]["place"] == 1 and top[0]["hours"] == 12
    page = client.get("/rating").get_data(as_text=True)
    assert "Екінші" in page and "Үздік ұйымдастырушылар" in page


def test_rating_hides_private_and_ignores_absent(make, client):
    org, vol, ghost = make.user("organizer"), make.user(name="Жария"), make.user(name="Жасырын Адам")
    _attend(make, vol, org, 1)
    _attend(make, ghost, org, 2)
    make.registration(make.user(), make.event(org, days=-1), "absent")
    get_db().execute("UPDATE users SET id_public=0 WHERE id=?", (ghost["id"],))
    get_db().commit()
    top = rs.top_volunteers()
    names = [v["name"] for v in top]
    assert "Жасырын Адам" not in names and "Жасырын ерікті" in names and len(top) == 2
    assert next(v for v in top if v["name"] == "Жасырын ерікті")["code"] is None
    assert "Жасырын Адам" not in client.get("/rating").get_data(as_text=True)


def test_rating_organizers_cities_and_period(make):
    org1, org2, vol = make.user("organizer"), make.user("organizer"), make.user()
    _attend(make, vol, org1, 2, city="Астана")
    _attend(make, vol, org2, 1, city="Алматы")
    orgs = rs.top_organizers()
    assert orgs[0]["attended"] == 2 and orgs[1]["attended"] == 1
    assert [c["city"] for c in rs.top_cities()] == ["Астана", "Алматы"]
    # 90 күн бұрынғы қатысу «осы ай» рейтингіне кірмейді, бірақ жалпы рейтингте бар
    old_vol = make.user(name="Ескі ерікті")
    make.registration(old_vol, make.event(org1, days=-90), "attended")
    assert "Ескі ерікті" in [v["name"] for v in rs.top_volunteers("all")]
    assert "Ескі ерікті" not in [v["name"] for v in rs.top_volunteers("month")]
    assert rs.normalize_period("zzz") == "all" and rs.normalize_period("month") == "month"


def test_rating_empty_and_bad_period(client):
    assert client.get("/rating?period=hack").status_code == 200
    assert "Әзірге деректер жоқ" in client.get("/rating").get_data(as_text=True)


# ---------- Ақылды іздеу ----------
def test_parse_city_with_case_suffix_and_topic():
    r = search_service.parse("экология Қызылордада", today=date(2026, 11, 18))
    assert r["city"] == "Қызылорда" and len(r["groups"]) == 1 and "қоқыс" in r["groups"][0]


def test_parse_time_words():
    today = date(2026, 11, 18)  # сәрсенбі
    assert search_service.parse("бүгін", today)["date_from"] == "2026-11-18"
    assert search_service.parse("ертең", today)["date_from"] == "2026-11-19"
    w = search_service.parse("осы апта", today)
    assert (w["date_from"], w["date_to"]) == ("2026-11-16", "2026-11-22")
    m = search_service.parse("осы ай", today)
    assert (m["date_from"], m["date_to"]) == ("2026-11-01", "2026-11-30")
    assert search_service.parse("", today)["groups"] == []


def test_smart_search_finds_by_topic_city_and_time(make):
    org = make.user("organizer")
    eco = make.event(org, days=2, title="Қала тазалығы", city="Қызылорда", description="Қоқыс жинау акциясы")
    other_city = make.event(org, days=2, title="Қала тазалығы", city="Астана", description="Қоқыс жинау")
    sport = make.event(org, days=2, title="Марафон", city="Қызылорда", description="Жүгіру")
    ids = lambda q: {e["id"] for e in event_service.search_events(q)}
    assert ids("экология Қызылордада") == {eco}
    assert ids("экология") == {eco, other_city}
    assert ids("спорт Қызылорда") == {sport}
    assert ids("Марафон Астана") == set()          # сөздер де, қала да сәйкес болуы керек
    today_ev = make.event(org, days=0, title="Бүгінгі акция", city="Астана")
    assert ids("бүгін") == {today_ev}
    assert ids("бүгін Алматы") == set()


def test_search_explicit_city_filter_wins(make):
    org = make.user("organizer")
    a = make.event(org, title="Тазалық", city="Астана")
    make.event(org, title="Тазалық", city="Алматы")
    got = {e["id"] for e in event_service.search_events("Тазалық Алматы", city="Астана")}
    assert got == {a}


def test_search_symbols_only_is_safe(make):
    org = make.user("organizer")
    e = make.event(org, title="Бір")
    # арнайы таңбалар SQL-ге әсер етпейді; сөзсіз сұрау сүзгі қоспайды
    assert {x["id"] for x in event_service.search_events("%%%")} == {e}
    assert event_service.search_events("'; DROP TABLE events;--") == []
    assert len(event_service.search_events("")) == 1


def test_catalog_shows_understood_chips(client, make):
    make.event(make.user("organizer"), title="Тазалау күні", city="Қызылорда")
    page = client.get("/events?q=экология+Қызылордада").get_data(as_text=True)
    assert "Түсінген іздеу" in page and "қала: Қызылорда" in page and "Тазалау күні" in page
    assert "Түсінген іздеу" not in client.get("/events").get_data(as_text=True)


# ---------- Іс-шара сағаты ----------
@pytest.mark.parametrize("bad", ["0", "25", "-1", "abc", "1.5"])
def test_event_hours_validation(bad):
    data = {"title": "Атау үш", "city": "Астана", "location": "Көше 1", "description": "",
            "event_date": when(3), "capacity": "5", "hours": bad}
    with pytest.raises(ValidationError):
        event_service.validate_event_data(data, True)


def test_event_hours_default_and_saved(make, client):
    org = make.user("organizer")
    login(client, org["email"])
    r = client.post("/organizer/events/new", data={"title": "Сағат сынағы", "city": "Астана",
                    "location": "Көше 1", "description": "", "event_date": when(4).replace(" ", "T"),
                    "capacity": "5", "hours": "6"})
    assert r.status_code == 302
    row = get_db().execute("SELECT hours FROM events WHERE title='Сағат сынағы'").fetchone()
    assert row["hours"] == 6
    assert event_service.validate_event_data({"title": "Атау үш", "city": "Астана", "location": "К",
                                              "event_date": when(3), "capacity": "5"}, True)["hours"] == 3


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    from app import create_app
    from config import TestConfig
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'volunteer',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        location TEXT NOT NULL, event_date TEXT NOT NULL, capacity INTEGER NOT NULL, organizer_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'published', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        INSERT INTO users (full_name,email,password_hash,role) VALUES ('Ескі','old@x.test','x','volunteer');""")
    con.commit(); con.close()
    app = create_app(TestConfig, DATABASE=path, CERTIFICATE_DIR=str(tmp_path / "c"))
    with app.app_context():
        row = get_db().execute("SELECT public_code, id_public FROM users").fetchone()
        assert row["public_code"].startswith("VID-") and row["id_public"] == 1
        assert "hours" in {r["name"] for r in get_db().execute("PRAGMA table_info(events)")}


def test_stopwords_are_ignored(make):
    e = make.event(make.user("organizer"), title="Тазалық күні")
    assert {x["id"] for x in event_service.search_events("Тазалық іс-шара және осы")} == {e}
    assert search_service.parse("Найди мероприятия")["groups"] == []


@pytest.mark.parametrize("path", [
    "/id/%00", "/id/" + "A" * 5000, "/id/ ", "/id/..%2f..", "/id/<script>", "/id/ВИД-ӘӘӘ",
    "/id/VID-X/qr.svg", "/rating?period=%00", "/rating?period[]=x",
    "/events?q=%00", "/events?q=" + "ж" * 5000, "/events?q=бүгін+бүгін+осы+ай+осы+апта",
    "/events?q=%25%5F%5C", "/events?q=" + "'+OR+1=1--",
])
def test_new_routes_never_500(client, path):
    assert client.get(path).status_code in (200, 302, 400, 404)
