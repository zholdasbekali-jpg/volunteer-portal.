"""FR-03, FR-06: каталог, іздеу, сүзгілер, іс-шараларды басқару және иелік құқығы."""
import pytest

from app.errors import NotFound, PermissionDenied, ValidationError
from app.services import event_service as es
from conftest import PASSWORD, login, when


def form(**kw):
    data = {"title": "Саябақты тазалау", "description": "Сипаттама", "city": "Қызылорда", "location": "Орталық саябақ",
            "event_date": when(7).replace(" ", "T"), "capacity": "10"}
    data.update(kw)
    return data


def test_create_event(ctx, make):
    org = make.user("organizer")
    eid = es.create_event(org, form())
    e = es.get_event(eid)
    assert e["title"] == "Саябақты тазалау" and e["capacity"] == 10
    assert e["organizer_id"] == org["id"] and e["status"] == "published"


@pytest.mark.parametrize("bad", [
    {"title": ""}, {"title": "ab"}, {"location": ""}, {"city": ""}, {"city": "Атлантида"}, {"capacity": "0"}, {"capacity": "-3"},
    {"capacity": "abc"}, {"capacity": "999999"}, {"event_date": "ертең"}, {"event_date": when(-2)},
])
def test_create_event_validation(ctx, make, bad):
    with pytest.raises(ValidationError):
        es.create_event(make.user("organizer"), form(**bad))


def test_volunteer_cannot_create_event(ctx, make):
    with pytest.raises(PermissionDenied):
        es.create_event(make.user("volunteer"), form())


def test_owner_can_update_but_other_organizer_cannot(ctx, make):
    owner, other = make.user("organizer"), make.user("organizer")
    eid = make.event(owner)
    es.update_event(owner, eid, form(title="Жаңа атау"))
    assert es.get_event(eid)["title"] == "Жаңа атау"
    with pytest.raises(PermissionDenied):
        es.update_event(other, eid, form(title="Бұзу"))
    with pytest.raises(PermissionDenied):
        es.cancel_event(other, eid)
    with pytest.raises(PermissionDenied):
        es.delete_event(other, eid)
    assert es.get_event(eid)["title"] == "Жаңа атау"


def test_admin_can_manage_any_event(ctx, make):
    org, adm = make.user("organizer"), make.user("admin")
    eid = make.event(org)
    es.cancel_event(adm, eid)
    assert es.get_event(eid)["status"] == "cancelled"
    es.restore_event(adm, eid)
    assert es.get_event(eid)["status"] == "published"


def test_cannot_reduce_capacity_below_registered(ctx, make):
    org = make.user("organizer")
    eid = make.event(org, capacity=5)
    for _ in range(3):
        make.registration(make.user(), eid)
    with pytest.raises(ValidationError):
        es.update_event(org, eid, form(capacity="2"))
    es.update_event(org, eid, form(capacity="3"))


def test_cancel_and_delete_event(ctx, make):
    org = make.user("organizer")
    eid = make.event(org)
    make.registration(make.user(), eid)
    es.cancel_event(org, eid)
    assert es.get_event(eid)["status"] == "cancelled"
    es.delete_event(org, eid)
    assert es.get_event(eid) is None
    with pytest.raises(NotFound):
        es.delete_event(org, eid)


def test_search_and_filters(ctx, make):
    org = make.user("organizer")
    make.event(org, title="Саябақ тазалау", days=3)
    make.event(org, title="Ағаш отырғызу", days=10)
    make.event(org, title="Өткен акция", days=-4)
    make.event(org, title="Тоқтатылған жоба", days=6, status="cancelled")
    assert [e["title"] for e in es.search_events(q="саябақ")] == ["Саябақ тазалау"]
    assert len(es.search_events(status="upcoming")) == 2
    assert [e["title"] for e in es.search_events(status="past")] == ["Өткен акция"]
    assert [e["title"] for e in es.search_events(status="cancelled")] == ["Тоқтатылған жоба"]
    assert len(es.search_events()) == 3                       # тоқтатылғандар әдепкіде көрсетілмейді
    day = when(10)[:10]
    assert [e["title"] for e in es.search_events(date=day)] == ["Ағаш отырғызу"]
    assert es.search_events(q="100%") == []                   # LIKE-таңбалары экрандалған
    with pytest.raises(ValidationError):
        es.search_events(date="31-31-2026")
    up, past = es.split_upcoming_past(es.search_events())
    assert len(up) == 2 and len(past) == 1


def test_free_spots_count_in_catalog(ctx, make):
    org = make.user("organizer")
    eid = make.event(org, capacity=4)
    make.registration(make.user(), eid)
    e = es.get_event(eid)
    assert e["registered_count"] == 1 and e["capacity"] - e["registered_count"] == 3


def test_http_catalog_detail_and_404(client, make):
    org = make.user("organizer")
    eid = make.event(org, title="Көрнекті іс-шара")
    assert "Көрнекті іс-шара" in client.get("/events").get_data(as_text=True)
    assert client.get(f"/events/{eid}").status_code == 200
    assert client.get("/events/99999").status_code == 404
    assert client.get("/events?status=hacked&date=bad").status_code == 200   # қате параметр құлатпайды


def test_http_create_edit_by_owner_and_403_for_other(client, make):
    owner, other = make.user("organizer"), make.user("organizer")
    login(client, owner["email"])
    r = client.post("/organizer/events/new", data=form(), follow_redirects=True)
    assert "сәтті құрылды" in r.get_data(as_text=True)
    eid = es.search_events()[0]["id"]
    client.post("/logout")
    login(client, other["email"])
    assert client.get(f"/organizer/events/{eid}/edit").status_code == 403
    assert client.post(f"/organizer/events/{eid}/edit", data=form(title="Бұзу")).status_code == 403
    assert client.post(f"/organizer/events/{eid}/delete").status_code == 403
    assert client.get(f"/organizer/events/{eid}/participants").status_code == 403
    assert es.get_event(eid)["title"] == "Саябақты тазалау"


def test_http_form_error_message_shown(client, make):
    org = make.user("organizer")
    login(client, org["email"])
    r = client.post("/organizer/events/new", data=form(capacity="0"))
    assert "1 мен" in r.get_data(as_text=True)


def test_city_stored_and_shown_in_full_address(ctx, make):
    org = make.user("organizer")
    eid = es.create_event(org, form(city="Астана", location="Достық көшесі, 5"))
    e = es.get_event(eid)
    assert e["city"] == "Астана" and es.full_address(e) == "Астана, Достық көшесі, 5"


def test_search_by_city_and_text(ctx, make):
    org = make.user("organizer")
    make.event(org, title="Астанадағы акция", city="Астана")
    make.event(org, title="Алматыдағы акция", city="Алматы")
    assert [e["title"] for e in es.search_events(city="Алматы")] == ["Алматыдағы акция"]
    assert len(es.search_events(city="Атлантида")) == 2           # белгісіз қала сүзгісі елеусіз қалады
    assert [e["title"] for e in es.search_events(q="астана")] == ["Астанадағы акция"]  # қала бойынша мәтіндік іздеу


def test_old_database_without_city_is_migrated(tmp_path):
    """Қала бағаны жоқ ескі қор деректерін жоғалтпай жаңа схемаға көшеді."""
    import sqlite3
    from app import create_app
    from config import TestConfig
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'volunteer', created_at TEXT NOT NULL DEFAULT '2026-01-01');
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL, event_date TEXT NOT NULL, capacity INTEGER NOT NULL, organizer_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'published', created_at TEXT NOT NULL DEFAULT '2026-01-01');
        INSERT INTO users (full_name, email, password_hash, role) VALUES ('Ұйым', 'o@example.test', 'x', 'organizer');
        INSERT INTO events (title, location, event_date, capacity, organizer_id) VALUES ('Ескі іс-шара', 'Көше 1', '2030-01-01 10:00', 5, 1);
    """)
    conn.close()
    app = create_app(TestConfig, DATABASE=path, CERTIFICATE_DIR=str(tmp_path / "c"))
    with app.app_context():
        e = es.get_event(1)
        assert e["title"] == "Ескі іс-шара" and e["city"] == "" and es.full_address(e) == "Көше 1"


def test_http_city_filter_and_form(client, make):
    org = make.user("organizer")
    make.event(org, title="Қызылордалық", city="Қызылорда")
    make.event(org, title="Шымкенттік", city="Шымкент")
    page = client.get("/events?city=Шымкент").get_data(as_text=True)
    assert "Шымкенттік" in page and "Қызылордалық" not in page
    login(client, org["email"])
    form_page = client.get("/organizer/events/new").get_data(as_text=True)
    assert 'name="city"' in form_page and "Қызылорда" in form_page
    r = client.post("/organizer/events/new", data=form(city="Атлантида"))
    assert "Қаланы тізімнен таңдаңыз" in r.get_data(as_text=True)


def test_participants_csv_export_and_permissions(client, make):
    owner, other, vol = make.user("organizer"), make.user("organizer"), make.user("volunteer", name="=HYPERLINK(1)")
    eid = make.event(owner)
    make.registration(vol, eid, status="attended")
    url = f"/organizer/events/{eid}/participants.csv"
    assert client.get(url).status_code in (302, 401)          # кірмеген
    login(client, other["email"])
    assert client.get(url).status_code == 403                  # басқа ұйымдастырушы
    client.post("/logout")
    login(client, owner["email"])
    r = client.get(url)
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]
    text = r.get_data(as_text=True)
    assert text.startswith("﻿") and "Қатысты" in text and vol["email"] in text
    assert "'=HYPERLINK" in text and ";=HYPERLINK" not in text    # формула енгізуінен қорғау
    assert client.get("/organizer/events/9999/participants.csv").status_code == 404
