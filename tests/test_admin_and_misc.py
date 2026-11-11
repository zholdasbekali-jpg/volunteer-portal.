"""Әкімші панелі, рөл шектеулері (HTTP), демо-деректер, CLI, қате беттері."""
import os

from app.database import get_db
from app.services import auth_service, certificate_service as cs
from app.services import event_service as es
from conftest import PASSWORD, login


def test_admin_dashboard_and_user_management(client, make):
    adm, vol = make.user("admin"), make.user("volunteer", name="Басқарылатын Ерікті")
    login(client, adm["email"])
    page = client.get("/admin/").get_data(as_text=True)
    assert "Басқарылатын Ерікті" in page and "Әкімші панелі" in page
    r = client.post(f"/admin/users/{vol['id']}/role", data={"role": "organizer"}, follow_redirects=True)
    assert "рөлі өзгертілді" in r.get_data(as_text=True)
    assert auth_service.get_user(vol["id"])["role"] == "organizer"
    r = client.post(f"/admin/users/{adm['id']}/role", data={"role": "volunteer"}, follow_redirects=True)
    assert "өз рөліңізді" in r.get_data(as_text=True).lower()          # өзін өзгерте алмайды
    r = client.post(f"/admin/users/{vol['id']}/delete", follow_redirects=True)
    assert "жойылды" in r.get_data(as_text=True)
    assert client.post("/admin/users/9999/delete").status_code == 404


def test_admin_actions_forbidden_for_others(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    login(client, org["email"])
    assert client.post(f"/admin/users/{vol['id']}/role", data={"role": "admin"}).status_code == 403
    assert client.post(f"/admin/users/{vol['id']}/delete").status_code == 403
    assert auth_service.get_user(vol["id"])["role"] == "volunteer"


def test_admin_manages_any_event_over_http(client, make):
    adm, org = make.user("admin"), make.user("organizer")
    eid = make.event(org, title="Басқа адамның іс-шарасы")
    login(client, adm["email"])
    assert client.get(f"/organizer/events/{eid}/edit").status_code == 200
    client.post(f"/organizer/events/{eid}/cancel")
    assert es.get_event(eid)["status"] == "cancelled"
    client.post(f"/organizer/events/{eid}/restore")
    assert es.get_event(eid)["status"] == "published"
    client.post(f"/organizer/events/{eid}/delete")
    assert es.get_event(eid) is None


def test_organizer_dashboard_and_actions_over_http(client, make):
    org = make.user("organizer")
    eid = make.event(org, title="Менің іс-шарам")
    login(client, org["email"])
    assert "Менің іс-шарам" in client.get("/organizer").get_data(as_text=True)
    client.post(f"/organizer/events/{eid}/cancel")
    assert es.get_event(eid)["status"] == "cancelled"
    client.post(f"/organizer/events/{eid}/restore")
    assert es.get_event(eid)["status"] == "published"
    r = client.post(f"/organizer/events/{eid}/edit",
                    data={"title": "Жаңартылған", "description": "", "city": "Астана", "location": "Орын",
                          "event_date": "2030-01-01T10:00", "capacity": "5"}, follow_redirects=True)
    assert "Өзгерістер сақталды" in r.get_data(as_text=True)
    assert client.get(f"/organizer/events/{eid}/participants").status_code == 200
    client.post(f"/organizer/events/{eid}/delete")
    assert client.get(f"/events/{eid}").status_code == 404
    assert client.get("/organizer/events/9999/edit").status_code == 404
    assert client.get("/organizer/events/9999/participants").status_code == 404


def test_volunteer_cannot_use_organizer_actions(client, make):
    org, vol = make.user("organizer"), make.user("volunteer")
    eid = make.event(org)
    rid = make.registration(vol, eid)
    login(client, vol["email"])
    assert client.post(f"/organizer/events/{eid}/delete").status_code == 403
    assert client.post(f"/organizer/events/{eid}/cancel").status_code == 403
    assert client.post(f"/registrations/{rid}/status", data={"status": "attended"}).status_code == 403
    assert es.get_event(eid) is not None


def test_organizer_cannot_register_over_http(client, make):
    org = make.user("organizer")
    eid = make.event(org)
    login(client, org["email"])
    assert client.post(f"/events/{eid}/register").status_code == 403
    assert client.post("/events/9999/register").status_code == 403


def test_register_unknown_event_404_for_volunteer(client, make):
    login(client, make.user()["email"])
    assert client.post("/events/9999/register").status_code == 404
    assert client.post("/registrations/9999/cancel").status_code == 404


def test_cancel_other_users_registration_is_403(client, make):
    org, v1, v2 = make.user("organizer"), make.user(), make.user()
    rid = make.registration(v1, make.event(org))
    login(client, v2["email"])
    assert client.post(f"/registrations/{rid}/cancel").status_code == 403


def test_deleting_event_removes_certificate_files(ctx, make):
    org, vol = make.user("organizer"), make.user()
    eid = make.event(org, days=-2)
    rid = make.registration(vol, eid, "attended")
    cert = cs.issue_certificate(vol, rid)
    paths = es.delete_event(org, eid)
    cs.remove_files(paths)
    assert not os.path.exists(cert["pdf_path"])
    assert get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 0


def test_deleting_user_cascades(ctx, make):
    adm, org, vol = make.user("admin"), make.user("organizer"), make.user()
    rid = make.registration(vol, make.event(org, days=-2), "attended")
    cert = cs.issue_certificate(vol, rid)
    cs.remove_files(auth_service.delete_user(adm, vol["id"]))
    assert not os.path.exists(cert["pdf_path"])
    assert get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 0


def test_seed_demo_and_login(app, client):
    from app.seed import ADMIN_EMAIL, ADMIN_PASSWORD, seed_demo
    with app.app_context():
        assert "жүктелді" in seed_demo()
        assert "жүктелмеді" in seed_demo()          # қайта жүктелмейді
        assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 6
    assert "Қош келдіңіз" in login(client, ADMIN_EMAIL, ADMIN_PASSWORD).get_data(as_text=True)
    assert client.get("/statistics").status_code == 200
    for name in ("summary", "events", "fill"):
        assert client.get(f"/statistics/chart/{name}.png").status_code == 200


def test_cli_commands(app):
    runner = app.test_cli_runner()
    assert "дайын" in runner.invoke(args=["init-db"]).output
    assert "жүктелді" in runner.invoke(args=["seed-demo"]).output
    res = runner.invoke(args=["create-admin", "--email", "boss@example.test", "--name", "Бастық",
                              "--password", PASSWORD], input=PASSWORD + "\n")
    assert "құрылды" in res.output


def test_error_pages_and_headers(client):
    r = client.get("/no-such-page")
    assert r.status_code == 404 and "Бет табылмады" in r.get_data(as_text=True)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/logout").status_code == 405


def test_debug_is_off_by_default():
    from config import Config
    assert Config.DEBUG is False


def test_home_page_renders_stats(client, make):
    make.event(make.user("organizer"), title="Басты беттегі іс-шара")
    page = client.get("/").get_data(as_text=True)
    assert "Басты беттегі іс-шара" in page and "Бірге жақсылық жасайық" in page


def test_logo_present_on_every_page_and_served(client, make):
    """Логотип барлық беттерде көрінуі керек, ал файлдың өзі сервер арқылы қолжетімді."""
    org, vol, adm = make.user("organizer"), make.user("volunteer"), make.user("admin")
    eid = make.event(org)
    for url in ("/", "/events", f"/events/{eid}", "/login", "/register", "/verify/NONE", "/no-such-page"):
        body = client.get(url).get_data(as_text=True)
        assert "images/logo.png" in body, url
    for user, urls in ((vol, ("/my", "/certificates")),
                       (org, ("/organizer", "/statistics", "/organizer/events/new")),
                       (adm, ("/admin/",))):
        login(client, user["email"])
        for url in urls:
            assert "images/logo.png" in client.get(url).get_data(as_text=True), url
        client.post("/logout")
    import re
    href = re.search(r'href="(/static/images/logo\.png\?v=\d+)"|src="(/static/images/logo\.png\?v=\d+)"',
                     client.get("/").get_data(as_text=True))
    assert href, "логотип сілтемесінде кэш нұсқасы (?v=) болуы керек"
    r = client.get(href.group(1) or href.group(2))
    assert r.status_code == 200 and r.mimetype == "image/png"


def test_broken_logo_is_logged_not_silent(tmp_path, monkeypatch, caplog):
    from app.services import certificate_service as cs
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    monkeypatch.setattr(cs, "find_logo", lambda: str(bad))
    with caplog.at_level("WARNING"):
        assert cs._load_logo() is None
    assert "логотипін оқу мүмкін болмады" in caplog.text
