"""Қауіпсіздік: кіруді шектеу, заголовоктар, кукилер, прокси, сессия."""
import re

import pytest

from app import create_app
from app.errors import TooManyAttempts
from app.services import throttle_service as th
from config import TestConfig
from conftest import PASSWORD, login


def bad_login(client, email, n=1):
    for _ in range(n):
        last = client.post("/login", data={"email": email, "password": "wrong-pass-1"})
    return last


def test_account_locked_after_five_failures_even_with_correct_password(client, make):
    u = make.user("volunteer")
    assert bad_login(client, u["email"], 5).status_code == 200
    r = client.post("/login", data={"email": u["email"], "password": PASSWORD})
    assert r.status_code == 429 and "минуттан кейін" in r.get_data(as_text=True)
    assert "Қош келдіңіз" not in r.get_data(as_text=True)
    assert client.get("/my").status_code == 302                    # кіре алмады


def test_lock_is_case_insensitive_and_other_account_unaffected(client, make):
    a, b = make.user("volunteer"), make.user("volunteer")
    bad_login(client, a["email"].upper(), 5)
    assert client.post("/login", data={"email": a["email"], "password": PASSWORD}).status_code == 429
    assert login(client, b["email"]).status_code == 200 and client.get("/my").status_code == 200


def test_success_resets_counter(client, make):
    u = make.user("volunteer")
    bad_login(client, u["email"], 4)
    login(client, u["email"]); client.post("/logout")
    bad_login(client, u["email"], 4)
    assert client.post("/login", data={"email": u["email"], "password": PASSWORD}, follow_redirects=True).status_code == 200


def test_throttle_service_window_lock_expiry_and_ip(ctx):
    for i in range(5):
        th.record_failure("x@example.test", "1.1.1.1", now=1000.0 + i)
    with pytest.raises(TooManyAttempts) as e:
        th.check("x@example.test", "9.9.9.9", now=1010.0)
    assert "минут" in e.value.message
    th.check("x@example.test", "9.9.9.9", now=1000.0 + th.LOCK_SECONDS + 10)   # бұғат аяқталды
    # IP бойынша жалпы шек: әр түрлі email-дармен
    for i in range(th.LIMITS["i"]):
        th.record_failure(f"u{i}@example.test", "2.2.2.2", now=5000.0)
    with pytest.raises(TooManyAttempts):
        th.check("new@example.test", "2.2.2.2", now=5001.0)
    # терезеден тыс сәтсіздіктер санала бермейді
    th.record_failure("old@example.test", "3.3.3.3", now=1.0)
    th.record_failure("old@example.test", "3.3.3.3", now=1.0 + th.WINDOW_SECONDS + 5)
    th.check("old@example.test", "3.3.3.3", now=2.0 + th.WINDOW_SECONDS)


def test_security_headers_present(client, make):
    r = client.get("/")
    h = r.headers
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and "script-src 'self'" in h["Content-Security-Policy"]
    assert "'unsafe-inline'" not in h["Content-Security-Policy"].split("script-src")[1].split(";")[0]
    assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
    assert "camera=(self)" in h["Permissions-Policy"] and h["Referrer-Policy"]
    assert "Strict-Transport-Security" not in h              # http-де HSTS жоқ
    assert "no-store" not in h.get("Cache-Control", "")      # қонақ беті кэштеле алады


def test_private_pages_are_not_cached_but_static_is(client, make):
    u = make.user("volunteer")
    login(client, u["email"])
    assert client.get("/my").headers["Cache-Control"] == "no-store"
    assert client.get("/cabinet/").headers["Cache-Control"] == "no-store"
    assert client.get("/static/css/style.css").headers.get("Cache-Control") != "no-store"


@pytest.mark.parametrize("role", ["volunteer", "organizer", "admin"])
def test_no_inline_scripts_or_handlers_anywhere(client, make, role):
    """CSP script-src 'self' жұмыс істеуі үшін: беттерде inline скрипт пен on*= атрибуттары жоқ."""
    u = make.user(role)
    org = u if role == "organizer" else make.user("organizer")
    eid = make.event(org)
    login(client, u["email"])
    paths = ["/", "/events", f"/events/{eid}", "/verify", "/cabinet/", "/my", "/certificates", "/organizer",
             "/statistics", "/admin/", "/organizer/events/new", f"/organizer/events/{eid}/participants",
             f"/organizer/events/{eid}/checkin"]
    for path in paths:
        r = client.get(path)
        if r.status_code != 200:
            continue
        html = r.get_data(as_text=True)
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), path
        assert not re.search(r"\son[a-z]+\s*=", html, re.I), path
        assert "javascript:" not in html.lower(), path


def test_session_cookie_flags(tmp_path):
    app = create_app(TestConfig, DATABASE=str(tmp_path / "s.db"), CERTIFICATE_DIR=str(tmp_path / "c"),
                     SESSION_COOKIE_SECURE=True)
    c = app.test_client()
    r = c.get("/login", base_url="https://localhost")
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Secure" in cookie
    assert "Strict-Transport-Security" in r.headers


def test_session_is_renewed_on_login(client, make):
    u = make.user("volunteer")
    client.get("/login")
    with client.session_transaction() as s:
        s["junk"] = "attacker-controlled"
    login(client, u["email"])
    with client.session_transaction() as s:
        assert "junk" not in s


def test_trust_proxy_uses_forwarded_scheme_and_ip(tmp_path):
    app = create_app(TestConfig, DATABASE=str(tmp_path / "p.db"), CERTIFICATE_DIR=str(tmp_path / "c"),
                     TRUST_PROXY=True)
    seen = {}

    @app.route("/_probe")
    def probe():
        from flask import request
        seen.update(root=request.url_root, ip=request.remote_addr)
        return "ok"

    app.test_client().get("/_probe", headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "5.6.7.8",
                                              "X-Forwarded-Host": "portal.example.kz"})
    assert seen == {"root": "https://portal.example.kz/", "ip": "5.6.7.8"}


def test_forged_forwarded_headers_ignored_without_trust_proxy(app):
    seen = {}

    @app.route("/_probe")
    def probe():
        from flask import request
        seen["ip"] = request.remote_addr
        return "ok"

    app.test_client().get("/_probe", headers={"X-Forwarded-For": "5.6.7.8"})
    assert seen["ip"] != "5.6.7.8"


def test_role_escalation_via_forms_is_impossible(client, make):
    from app.errors import ValidationError  # noqa: F401
    r = client.post("/register", data={"full_name": "Хакер", "email": "h@example.test", "password": "Hack12345",
                                       "role": "admin"})
    assert r.status_code == 200 and "рөлмен тіркелуге болмайды" in r.get_data(as_text=True)
    v = make.user("volunteer")
    login(client, v["email"])
    assert client.post(f"/admin/users/{v['id']}/role", data={"role": "admin"}).status_code == 403
    assert client.post("/cabinet/profile", data={"full_name": "Тест", "role": "admin"}).status_code == 302
    from app.services import auth_service
    assert auth_service.get_user(v["id"])["role"] == "volunteer"
