"""Басқару панельдерінің сүзгілері, сұрыптауы және жаппай әрекеттері."""
from app.database import get_db
from conftest import login


def _status(registration_id):
    return get_db().execute("SELECT status FROM registrations WHERE id=?", (registration_id,)).fetchone()["status"]


def test_admin_dashboard_search_filters_and_sort(client, make):
    adm = make.user("admin")
    make.user("volunteer", name="Анна Ахметова", email="anna@example.test")
    make.user("organizer", name="Болат Органов", email="bolat@example.test")
    org = make.user("organizer", name="Ұйымдастырушы Сынақ")
    make.event(org, title="Экология Қызылорда", days=5)
    make.event(org, title="Спорт Астана", days=-5, status="cancelled", city="Астана")
    login(client, adm["email"])

    body = client.get("/admin/?tab=users&u_q=anna&u_role=volunteer").get_data(as_text=True)
    assert "Анна Ахметова" in body and "Болат Органов" not in body
    assert 'value="anna"' in body and 'value="volunteer" selected' in body

    body = client.get("/admin/?tab=users&u_role=organizer&u_sort=name").get_data(as_text=True)
    assert "Болат Органов" in body and "Анна Ахметова" not in body

    body = client.get("/admin/?tab=events&e_q=экология").get_data(as_text=True)
    assert "Экология Қызылорда" in body and "Спорт Астана" not in body
    body = client.get("/admin/?tab=events&e_status=past").get_data(as_text=True)
    assert "Спорт Астана" in body and "Экология Қызылорда" not in body
    body = client.get("/admin/?tab=regs&r_q=nonexistent").get_data(as_text=True)
    assert "Іздеу нәтижесі жоқ" in body
    assert "tab-pane fade show active" in body


def test_admin_dashboard_keeps_selected_tab(client, make):
    adm = make.user("admin")
    login(client, adm["email"])
    body = client.get("/admin/?tab=regs").get_data(as_text=True)
    assert '<div class="tab-pane fade show active" id="regs"' in body
    assert '<div class="tab-pane fade " id="users"' in body


def test_organizer_dashboard_search_and_status(client, make):
    org = make.user("organizer")
    make.event(org, title="Экология Қызылорда", days=5)
    make.event(org, title="Спорт Астана", days=5, city="Астана")
    login(client, org["email"])

    body = client.get("/organizer?q=астана").get_data(as_text=True)
    assert "Спорт Астана" in body and "Экология Қызылорда" not in body
    body = client.get("/organizer?status=past").get_data(as_text=True)
    assert "Іздеу нәтижесі жоқ" in body
    body = client.get("/organizer?sort=title").get_data(as_text=True)
    assert body.index("Спорт Астана") < body.index("Экология Қызылорда")


def test_participants_search_status_and_bulk_update(client, make):
    org = make.user("organizer")
    v1 = make.user("volunteer", name="Анна Волонтёр")
    v2 = make.user("volunteer", name="Болат Волонтёр")
    eid = make.event(org, capacity=4)
    r1 = make.registration(v1, eid)
    r2 = make.registration(v2, eid)
    login(client, org["email"])

    body = client.get(f"/organizer/events/{eid}/participants?q=анна").get_data(as_text=True)
    assert "Анна Волонтёр" in body and "Болат Волонтёр" not in body
    body = client.get(f"/organizer/events/{eid}/participants?status=attended").get_data(as_text=True)
    assert "Іздеу нәтижесі жоқ" in body

    r = client.post(f"/organizer/events/{eid}/participants/status",
                    data={"ids": [str(r1), str(r2)], "status": "attended", "q": "анна"},
                    follow_redirects=True)
    assert r.status_code == 200 and "Таңдалған тіркелімдер жаңартылды" in r.get_data(as_text=True)
    assert _status(r1) == "attended" and _status(r2) == "attended"
    assert "q=%D0%B0%D0%BD%D0%BD%D0%B0" in r.request.query_string.decode() or "q=анна" in r.request.query_string.decode()

    r = client.post(f"/organizer/events/{eid}/participants/status",
                    data={"status": "absent"}, follow_redirects=True)
    assert "Ештеңе таңдалмады" in r.get_data(as_text=True)
    assert _status(r1) == "attended"


def test_bulk_update_rejects_foreign_registration_and_bad_status(client, make):
    org1, org2, vol = make.user("organizer"), make.user("organizer"), make.user()
    e1, e2 = make.event(org1), make.event(org2)
    foreign = make.registration(vol, e2)
    login(client, org1["email"])
    url = f"/organizer/events/{e1}/participants/status"
    assert client.post(url, data={"ids": [str(foreign)], "status": "attended"}).status_code == 403
    assert _status(foreign) == "pending"
    own = make.registration(vol, e1)
    r = client.post(url, data={"ids": [str(own)], "status": "unknown"}, follow_redirects=True)
    assert "Белгісіз қатысу мәртебесі" in r.get_data(as_text=True)
    assert _status(own) == "pending"


def test_management_nav_is_grouped_for_staff_only(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    login(client, org["email"])
    body = client.get("/organizer").get_data(as_text=True)
    assert 'id="vp-manage-menu"' in body and "Басқару" in body
    assert "Ұйымдастырушы панелі" in body and "Статистика" in body
    client.post("/logout")
    login(client, vol["email"])
    body = client.get("/my").get_data(as_text=True)
    assert 'id="vp-manage-menu"' not in body
