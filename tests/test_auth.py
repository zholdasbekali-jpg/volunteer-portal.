"""FR-01, FR-02, NFR-01: тіркелу, авторизация, парольдер қауіпсіздігі, рөлдер."""
import pytest

from app.database import get_db
from app.errors import Conflict, PermissionDenied, ValidationError
from app.security import is_safe_next
from app.services import auth_service
from conftest import PASSWORD, login


def test_register_success(ctx):
    uid = auth_service.register_user("Асем Сәрсенбай", "Asem@Example.test", PASSWORD)
    row = auth_service.get_user(uid)
    assert row["email"] == "asem@example.test"      # email кіші әріпке келтіріледі
    assert row["role"] == "volunteer"


def test_register_duplicate_email_rejected(ctx):
    auth_service.register_user("Бірінші", "dup@example.test", PASSWORD)
    with pytest.raises(Conflict):
        auth_service.register_user("Екінші", "DUP@example.test", PASSWORD)


@pytest.mark.parametrize("name,email,password", [
    ("", "a@example.test", PASSWORD),              # аты бос
    ("Аты", "", PASSWORD),                          # email бос
    ("Аты", "not-an-email", PASSWORD),              # email форматы
    ("Аты", "a@example.test", ""),                  # пароль бос
    ("Аты", "a@example.test", "short1"),            # пароль қысқа
    ("Аты", "a@example.test", "onlyletters"),       # цифр жоқ
])
def test_register_validation(ctx, name, email, password):
    with pytest.raises(ValidationError):
        auth_service.register_user(name, email, password)


def test_cannot_self_register_as_admin(ctx):
    with pytest.raises(ValidationError):
        auth_service.register_user("Хакер", "h@example.test", PASSWORD, role="admin")


def test_password_is_hashed(ctx):
    uid = auth_service.register_user("Аты Жөні", "hash@example.test", PASSWORD)
    stored = auth_service.get_user(uid)["password_hash"]
    assert stored != PASSWORD and PASSWORD not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))


def test_login_success_and_wrong_password(ctx):
    auth_service.register_user("Аты Жөні", "login@example.test", PASSWORD)
    assert auth_service.authenticate("LOGIN@example.test", PASSWORD)["email"] == "login@example.test"
    with pytest.raises(ValidationError):
        auth_service.authenticate("login@example.test", "WrongPass1")
    with pytest.raises(ValidationError):   # бар емес email — бірдей хабарлама
        auth_service.authenticate("nobody@example.test", PASSWORD)
    with pytest.raises(ValidationError):
        auth_service.authenticate("", "")


def test_http_register_login_logout_flow(client):
    r = client.post("/register", data={"full_name": "Ерікті Бір", "email": "flow@example.test",
                                       "password": PASSWORD, "role": "volunteer"}, follow_redirects=True)
    assert "Тіркелу сәтті" in r.get_data(as_text=True)
    r = login(client, "flow@example.test")
    assert "Қош келдіңіз" in r.get_data(as_text=True)
    assert client.get("/my").status_code == 200
    client.post("/logout")
    assert client.get("/my").status_code == 302   # шыққаннан кейін қорғалған бет жабық


def test_http_login_wrong_password_shows_error(client, make):
    make.user(email="v@example.test")
    r = login(client, "v@example.test", "Qate12345")
    assert "қате" in r.get_data(as_text=True)


def test_http_duplicate_register_shows_message(client, make):
    make.user(email="taken@example.test")
    r = client.post("/register", data={"full_name": "Аты Жөні", "email": "taken@example.test",
                                       "password": PASSWORD}, follow_redirects=True)
    assert "бұрын тіркелген" in r.get_data(as_text=True)


def test_protected_pages_require_login(client):
    for url in ("/my", "/certificates", "/organizer", "/statistics", "/admin/", "/organizer/events/new"):
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"], url


def test_role_restrictions(client, make):
    vol, org, adm = make.user("volunteer"), make.user("organizer"), make.user("admin")
    login(client, vol["email"])
    assert client.get("/organizer").status_code == 403
    assert client.get("/admin/").status_code == 403
    assert client.get("/statistics").status_code == 403
    client.post("/logout")
    login(client, org["email"])
    assert client.get("/organizer").status_code == 200
    assert client.get("/admin/").status_code == 403
    assert client.get("/my").status_code == 403
    client.post("/logout")
    login(client, adm["email"])
    assert client.get("/admin/").status_code == 200


def test_open_redirect_blocked():
    assert is_safe_next("/events/1")
    assert not is_safe_next("https://evil.example/x")
    assert not is_safe_next("//evil.example")
    assert not is_safe_next("")
    # браузер "\\" белгісін "/" деп оқиды: "/\\evil.example" = "//evil.example"
    assert not is_safe_next("/\\evil.example")
    assert not is_safe_next("/\t/evil.example")


def test_login_next_redirect_safe(client, make):
    u = make.user(email="n@example.test")
    r = client.post("/login?next=https://evil.example", data={"email": u["email"], "password": PASSWORD})
    assert r.status_code == 302 and "evil.example" not in r.headers["Location"]


def test_csrf_is_enforced(app, make):
    app.config["CSRF_ENABLED"] = True
    c = app.test_client()
    r = c.post("/login", data={"email": "x@example.test", "password": PASSWORD})
    assert r.status_code == 400
    # жарамды токенмен өтеді
    page = c.get("/login").get_data(as_text=True)
    token = page.split('name="csrf_token" value="')[1].split('"')[0]
    r = c.post("/login", data={"email": "x@example.test", "password": PASSWORD, "csrf_token": token})
    assert r.status_code == 200


def test_admin_manage_users(ctx, make):
    adm, vol = make.user("admin"), make.user("volunteer")
    auth_service.set_user_role(adm, vol["id"], "organizer")
    assert auth_service.get_user(vol["id"])["role"] == "organizer"
    with pytest.raises(ValidationError):
        auth_service.set_user_role(adm, adm["id"], "volunteer")   # өз рөлін өзгерте алмайды
    with pytest.raises(PermissionDenied):
        auth_service.set_user_role(vol, adm["id"], "volunteer")
    assert len(auth_service.list_users()) == 2
    auth_service.delete_user(adm, vol["id"])
    assert auth_service.get_user(vol["id"]) is None
    with pytest.raises(PermissionDenied):
        auth_service.delete_user(vol, adm["id"])


def test_sql_injection_attempt_is_harmless(ctx, make):
    make.user(email="safe@example.test")
    with pytest.raises(ValidationError):
        auth_service.authenticate("' OR '1'='1", "x")
    assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_csrf_non_ascii_token_gives_400_not_500(app):
    app.config["CSRF_ENABLED"] = True
    c = app.test_client()
    c.get("/login")  # сессияда токен пайда болады
    r = c.post("/login", data={"email": "x@example.test", "password": PASSWORD, "csrf_token": "қате-é"})
    assert r.status_code == 400
