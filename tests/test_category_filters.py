"""V3 этап 3: санат сүзгісі әкімші мен ұйымдастырушы панельдерінде (қайта пайдалану, duplication жоқ)."""
from app.database import get_db
from app.models import CATEGORY_CODES, EVENT_CATEGORIES
from conftest import login


def set_category(event_id, code):
    get_db().execute("UPDATE events SET category=? WHERE id=?", (code, event_id))


def test_admin_filters_events_by_category(make, client):
    admin = make.user("admin")
    org = make.user("organizer")
    eco = make.event(org, title="Экологиялық іс")
    sport = make.event(org, title="Спорттық іс")
    set_category(eco, "ecology")
    set_category(sport, "sport")
    login(client, admin["email"])

    body = client.get("/admin/?tab=events&e_category=ecology").get_data(as_text=True)
    assert "Экологиялық іс" in body and "Спорттық іс" not in body
    assert 'name="e_category"' in body and 'value="ecology" selected' in body


def test_admin_category_filter_keeps_status_and_search(make, client):
    admin, org = make.user("admin"), make.user("organizer")
    a = make.event(org, title="Эко іс", status="published")
    make.event(org, title="Эко өткен", status="cancelled")
    set_category(a, "ecology")
    login(client, admin["email"])

    body = client.get("/admin/?tab=events&e_category=ecology&e_status=published&e_q=Эко").get_data(as_text=True)
    assert "Эко іс" in body and "Эко өткен" not in body
    assert 'name="e_status"' in body and 'value="published" selected' in body
    assert 'name="e_q" value="Эко"' in body


def test_admin_ignores_unknown_category(make, client):
    admin, org = make.user("admin"), make.user("organizer")
    a = make.event(org, title="Бір іс")
    set_category(a, "ecology")
    login(client, admin["email"])
    body = client.get("/admin/?tab=events&e_category='%20OR%201%3D1%20--").get_data(as_text=True)
    assert "Бір іс" in body and "OR 1=1" not in body


def test_organizer_filters_events_by_category(make, client):
    org = make.user("organizer")
    eco = make.event(org, title="Эко жиналыс")
    sport = make.event(org, title="Марафон")
    set_category(eco, "ecology")
    set_category(sport, "sport")
    login(client, org["email"])

    body = client.get("/organizer?category=sport").get_data(as_text=True)
    assert "Марафон" in body and "Эко жиналыс" not in body
    assert 'name="category"' in body and 'value="sport" selected' in body


def test_organizer_category_filter_keeps_status(make, client):
    org = make.user("organizer")
    a = make.event(org, title="Эко жария", status="published")
    b = make.event(org, title="Эко тоқтатылған", status="cancelled")
    set_category(a, "ecology")
    set_category(b, "ecology")
    login(client, org["email"])

    body = client.get("/organizer?category=ecology&status=published").get_data(as_text=True)
    assert "Эко жария" in body and "Эко тоқтатылған" not in body


def test_management_tables_show_category_badge(make, client):
    admin, org = make.user("admin"), make.user("organizer")
    ev = make.event(org, title="Мәдени кеш")
    set_category(ev, "culture")
    login(client, admin["email"])  # админу доступны обе панели; один логин на тест ( Flask-Login кэш в g )
    assert "Мәдениет" in client.get("/organizer").get_data(as_text=True)
    body = client.get("/admin/?tab=events").get_data(as_text=True)
    assert "Мәдениет" in body


def test_category_filter_options_use_existing_catalog(make, client):
    admin = make.user("admin")
    login(client, admin["email"])
    body = client.get("/admin/?tab=events").get_data(as_text=True)
    for code, label in EVENT_CATEGORIES:
        assert f'value="{code}"' in body and label in body
    assert set(CATEGORY_CODES) == {code for code, _ in EVENT_CATEGORIES}
