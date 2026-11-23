"""Этап 1: іс-шара санаттары (деректер қоры, тексеру, сүзгі, көрсету, көші-қон)."""
import pytest

from app import database
from app.database import get_db
from app.errors import ValidationError
from app.models import CATEGORY_CODES, CATEGORY_LABELS, EVENT_CATEGORIES
from app.services import event_service
from conftest import login, when


def form(**overrides):
    data = {"title": "Қала тазалығы", "description": "Сипаттама", "city": "Қызылорда",
            "location": "Орталық көше, 1", "event_date": when(5).replace(" ", "T"),
            "capacity": "10", "hours": "3"}
    data.update(overrides)
    return data


def make_event(org, **overrides):
    return event_service.create_event(org, form(**overrides))


def category_of(event_id):
    row = get_db().execute("SELECT category FROM events WHERE id = ?", (event_id,)).fetchone()
    return row["category"]


# ---------- модель мен көші-қон ----------

def test_category_catalog_is_consistent():
    assert len(CATEGORY_CODES) == len(set(CATEGORY_CODES)) == len(EVENT_CATEGORIES)
    assert "other" in CATEGORY_CODES and set(CATEGORY_LABELS) == set(CATEGORY_CODES)


def test_migration_adds_category_to_existing_events(ctx, make):
    db = get_db()
    org = make.user("organizer")
    ev = make.event(org)
    db.execute("DROP INDEX IF EXISTS idx_events_category")
    try:
        db.execute("ALTER TABLE events DROP COLUMN category")  # V1 қорының күйі: санат бағаны жоқ
    except Exception:
        pytest.skip("SQLite ескі: DROP COLUMN қолдамайды")
    database.init_db()
    assert category_of(ev) == "other"      # бұрынғы іс-шаралар «Басқа» болады
    database.init_db()                     # қайта іске қосу қате бермейді
    indexes = {r["name"] for r in db.execute("PRAGMA index_list(events)")}
    assert "idx_events_category" in indexes


# ---------- тексеру ----------

def test_create_with_category_and_default(ctx, make):
    org = make.user("organizer")
    assert category_of(make_event(org, category="ecology")) == "ecology"
    assert category_of(make_event(org)) == "other"                  # берілмесе — «Басқа»
    assert category_of(make_event(org, category="")) == "other"


@pytest.mark.parametrize("bad", ["unknown", "ECOLOGY", "ecology; DROP TABLE events",
                                 "' OR 1=1 --", "экология"])
def test_invalid_category_is_rejected(ctx, make, bad):
    org = make.user("organizer")
    with pytest.raises(ValidationError, match="Санатты"):
        make_event(org, category=bad)
    assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_update_changes_category_and_validates(ctx, make):
    org = make.user("organizer")
    ev = make_event(org, category="sport")
    event_service.update_event(org, ev, form(category="health"))
    assert category_of(ev) == "health"
    with pytest.raises(ValidationError):
        event_service.update_event(org, ev, form(category="nope"))
    assert category_of(ev) == "health"                              # қате болса, өзгермейді


# ---------- сүзгі ----------

def test_search_filters_by_category(ctx, make):
    org = make.user("organizer")
    eco = make_event(org, category="ecology", title="Саябақ тазалау")
    sport = make_event(org, category="sport", title="Марафон")
    other = make_event(org, title="Жалпы іс-шара")

    def ids(**kw):
        return {r["id"] for r in event_service.search_events(**kw)}

    assert ids(category="ecology") == {eco}
    assert ids(category="sport") == {sport}
    assert ids(category="other") == {other}
    assert ids() == {eco, sport, other}
    assert ids(category="culture") == set()


def test_unknown_category_filter_is_ignored_not_injected(ctx, make):
    org = make.user("organizer")
    a, b = make_event(org, category="ecology"), make_event(org, category="sport")
    for bad in ("zzz", "' OR '1'='1", "ecology' --", "ecology%"):
        assert {r["id"] for r in event_service.search_events(category=bad)} == {a, b}


def test_category_combines_with_city_status_and_text(ctx, make):
    org = make.user("organizer")
    kz = make_event(org, category="ecology", city="Қызылорда", title="Қала тазалау")
    ast = make_event(org, category="ecology", city="Астана", title="Қала тазалау")
    make_event(org, category="sport", city="Қызылорда", title="Қала жарысы")
    found = event_service.search_events(q="тазалау", city="Қызылорда", category="ecology")
    assert {r["id"] for r in found} == {kz}
    upcoming = event_service.search_events(category="ecology", status="upcoming")
    assert {r["id"] for r in upcoming} == {kz, ast}


# ---------- беттер ----------

def test_catalog_page_filters_and_keeps_other_filters(make, client):
    org = make.user("organizer")
    make_event(org, category="ecology", title="Экология акциясы")
    make_event(org, category="sport", title="Спорт күні")
    body = client.get("/events?category=ecology").get_data(as_text=True)
    assert "Экология акциясы" in body and "Спорт күні" not in body
    assert 'name="category" value="ecology"' in body    # іздеу формасы санатты жоғалтпайды
    body = client.get("/events?category=sport&city=Қызылорда&q=күні").get_data(as_text=True)
    assert "category=sport" in body and "Спорт күні" in body
    # санат түймелері басқа сүзгілерді сақтайды
    assert "city=%D2%9A%D1%8B%D0%B7%D1%8B%D0%BB%D0%BE%D1%80%D0%B4%D0%B0" in body


def test_catalog_ignores_garbage_category(make, client):
    org = make.user("organizer")
    make_event(org, category="ecology", title="Бір")
    make_event(org, category="sport", title="Екі")
    body = client.get("/events?category=%27%20OR%201%3D1%20--").get_data(as_text=True)
    assert "Бір" in body and "Екі" in body and "OR 1=1" not in body


def test_event_form_has_categories_and_saves(make, client):
    org = make.user("organizer")
    login(client, org["email"])
    page = client.get("/organizer/events/new").get_data(as_text=True)
    for code in CATEGORY_CODES:
        assert f'value="{code}"' in page
    r = client.post("/organizer/events/new", data=form(category="culture"), follow_redirects=True)
    assert r.status_code == 200
    ev = get_db().execute("SELECT id, category FROM events").fetchone()
    assert ev["category"] == "culture"
    edit = client.get(f"/organizer/events/{ev['id']}/edit").get_data(as_text=True)
    assert 'value="culture" selected' in edit           # өңдеуде таңдалған санат көрінеді
    client.post(f"/organizer/events/{ev['id']}/edit", data=form(category="health"),
                follow_redirects=True)
    assert category_of(ev["id"]) == "health"


def test_event_form_rejects_bad_category_with_message(make, client):
    org = make.user("organizer")
    login(client, org["email"])
    r = client.post("/organizer/events/new", data=form(category="hack"), follow_redirects=True)
    assert "Санатты тізімнен таңдаңыз." in r.get_data(as_text=True)
    assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


@pytest.mark.parametrize("lang, label", [("kk", "Қайырымдылық"), ("ru", "Благотворительность"),
                                         ("en", "Charity")])
def test_category_label_shown_in_each_language(make, client, lang, label):
    org = make.user("organizer")
    ev = make_event(org, category="charity")
    client.get(f"/lang/{lang}")
    assert label in client.get(f"/events/{ev}").get_data(as_text=True)
    assert label in client.get("/events").get_data(as_text=True)  # картада да, санат түймесінде де
