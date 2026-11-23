"""Көптілділік (kk/ru/en): аудармалар толықтығы, тіл ауыстыру, беттер, хабарламалар, құжаттар."""
import ast
import json
import re
from datetime import date
from pathlib import Path

import pytest

from app import i18n
from app.database import get_db
from app.models import CATEGORY_LABELS, CITIES, EVENT_STATUS_LABELS, REG_STATUS_LABELS, ROLE_LABELS
from app.services import certificate_service as cs, search_service
from conftest import PASSWORD, login

APP_DIR = Path(__file__).resolve().parent.parent / "app"
CYR = "А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі"
PLACEHOLDER = re.compile(r"\{\w+\}")


def _catalog(lang):
    return json.loads((APP_DIR / "translations" / f"{lang}.json").read_text(encoding="utf-8"))


def _template_literals():
    """Шаблондардағы _('...') және '...' түріндегі барлық қазақша жолдар."""
    found = {}
    for f in (APP_DIR / "templates").rglob("*.html"):
        for m in re.finditer(r"'((?:[^'\\\n]|\\.)*[%s](?:[^'\\\n]|\\.)*)'" % CYR, f.read_text(encoding="utf-8")):
            found.setdefault(m.group(1).replace("\\'", "'"), f.name)
    return found


def _fstring_key(node):
    names, parts = set(), []
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(v.value)
        else:
            e = v.value
            n = e.id if isinstance(e, ast.Name) else e.attr if isinstance(e, ast.Attribute) else "n"
            base, i = n, 2
            while n in names:
                n, i = f"{base}{i}", i + 1
            names.add(n)
            parts.append("{%s}" % n)
    return "".join(parts)


def _user_messages():
    """raise XxxError("...") және flash("...") ішіндегі қазақша хабарламалар (пайдаланушыға көрсетіледі)."""
    found = {}
    for f in list((APP_DIR / "services").glob("*.py")) + list(APP_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            known = ("Conflict", "NotFound", "PermissionDenied", "TooManyAttempts", "flash")
            if not (fn.endswith("Error") or fn in known):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.JoinedStr):
                text = _fstring_key(arg)
            else:
                text = arg.value if isinstance(arg, ast.Constant) else None
            if isinstance(text, str) and re.search("[%s]" % CYR, text):
                found.setdefault(text, f"{f.name}:{node.lineno}")
    return found


# ---------- аударма файлдары ----------

def test_catalogs_have_same_keys_and_placeholders():
    ru, en = _catalog("ru"), _catalog("en")
    assert ru.keys() == en.keys()
    for key in ru:
        found = [sorted(PLACEHOLDER.findall(text)) for text in (key, ru[key], en[key])]
        assert found[0] == found[1] == found[2], key
        assert ru[key].strip() and en[key].strip(), key


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_template_string_is_translated(lang):
    missing = [f"{src}: {k}" for k, src in _template_literals().items() if k not in _catalog(lang)]
    assert not missing, missing


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_user_message_is_translated(lang):
    cat = _catalog(lang)
    patterns = [re.compile(re.sub(r"\\\{\w+\\\}", ".+?", re.escape(k)), re.DOTALL)
                for k in cat if PLACEHOLDER.search(k)]
    missing = [f"{src}: {k}" for k, src in _user_messages().items()
               if k not in cat and not any(p.fullmatch(k) for p in patterns)]
    assert not missing, missing


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_labels_and_cities_are_translated(lang):
    cat = _catalog(lang)
    labels = [*ROLE_LABELS.values(), *EVENT_STATUS_LABELS.values(), *REG_STATUS_LABELS.values(),
              *CITIES, *CATEGORY_LABELS.values()]
    assert [x for x in labels if x not in cat] == []


# ---------- translate() ----------

def test_translate_exact_params_fallback_and_default():
    assert i18n.translate("Кіру", "ru") == "Войти"
    assert i18n.translate("Кіру", "en") == "Log in"
    assert i18n.translate("Кіру", "kk") == "Кіру"                          # әдепкі тіл өзгермейді
    assert i18n.translate("Бұл жолдың аудармасы жоқ", "en") == "Бұл жолдың аудармасы жоқ"   # табылмаса — түпнұсқа
    assert i18n.translate("{n} сағ", "ru", n=3) == "3 ч"
    assert i18n.translate("{n} сағ", "kk", n=3) == "3 сағ"
    assert i18n.translate("", "ru") == "" and i18n.translate(None, "ru") == ""


def test_translate_formatted_message_and_nested_city():
    assert i18n.translate("Қош келдіңіз, Айгүл!", "ru") == "Добро пожаловать, Айгүл!"
    assert i18n.translate("қала: Қызылорда", "en") == "city: Kyzylorda"     # қала атауы да аударылады
    assert i18n.translate("Қатысушылар санын 4-тен азайтуға болмайды: осынша эріктілер тіркелген.", "en").startswith(
        "You cannot reduce the number of participants below 4")


def test_translate_does_not_reformat_user_data_with_braces():
    out = i18n.translate("Қош келдіңіз, {x}!", "ru")                        # құрамында { } бар пайдаланушы мәтіні
    assert out == "Добро пожаловать, {x}!"
    assert i18n.translate("Ұйымдастырушы: {name}", "en", name="{n}") == "Organizer: {n}"


def test_format_date_in_three_languages():
    assert i18n.format_date("2026-05-01 10:00", lang="kk") == "1 мамыр 2026, 10:00"
    assert i18n.format_date("2026-05-01 10:00", lang="ru") == "1 мая 2026, 10:00"
    assert i18n.format_date("2026-05-01 10:00", lang="en") == "1 May 2026, 10:00"
    assert i18n.format_date("2026-05-01 10:00", with_time=False, lang="en") == "1 May 2026"
    assert i18n.format_date("", lang="ru") == ""


# ---------- тіл ауыстыру ----------

def test_default_language_is_kazakh(client):
    r = client.get("/login")
    assert 'lang="kk"' in r.get_data(as_text=True) and "Жүйеге кіру" in r.get_data(as_text=True)


@pytest.mark.parametrize("code, marker", [("ru", "Вход в систему"), ("en", "Log in")])
def test_switch_language_changes_pages(client, code, marker):
    r = client.get(f"/lang/{code}?next=/login", follow_redirects=True)
    body = r.get_data(as_text=True)
    assert f'lang="{code}"' in body and marker in body and "Жүйеге кіру" not in body


def test_unknown_language_is_404(client):
    assert client.get("/lang/de").status_code == 404
    assert client.get("/lang/kk-KZ").status_code == 404


@pytest.mark.parametrize("target", ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"])
def test_language_switch_rejects_open_redirect(client, target):
    r = client.get("/lang/ru", query_string={"next": target})
    assert r.status_code == 302 and "evil" not in r.headers["Location"] and r.headers["Location"].startswith("/")


def test_language_is_saved_for_logged_in_user_and_restored_on_login(app, make, client):
    v = make.user("volunteer")
    login(client, v["email"])
    client.get("/lang/ru")
    assert get_db().execute("SELECT lang FROM users WHERE id=?", (v["id"],)).fetchone()["lang"] == "ru"
    client.post("/logout")             # ортақ app-контекстте бір мезгілде бір ғана кірген пайдаланушы
    other = app.test_client()                                               # жаңа құрылғы: тіл таңдалмаған
    login(other, v["email"])
    with other.session_transaction() as s:
        assert s["lang"] == "ru"
    assert "Мои регистрации" in other.get("/my").get_data(as_text=True)


def test_language_chosen_before_login_survives_session_reset(app, make, client):
    v = make.user("volunteer")
    client.get("/lang/en")
    login(client, v["email"])
    with client.session_transaction() as s:
        assert s["lang"] == "en"
    assert get_db().execute("SELECT lang FROM users WHERE id=?", (v["id"],)).fetchone()["lang"] == "en"


def test_language_survives_logout(app, make, client):
    v = make.user("volunteer")
    client.get("/lang/ru")
    login(client, v["email"])
    client.post("/logout")
    with client.session_transaction() as s:
        assert s["lang"] == "ru"


def test_set_user_lang_validates(ctx, make):
    from app.errors import ValidationError
    from app.services import auth_service
    u = make.user()
    with pytest.raises(ValidationError):
        auth_service.set_user_lang(u["id"], "de")


# ---------- хабарламалар, қателер, құжаттар ----------

def test_flash_and_validation_messages_are_translated(make, client):
    v = make.user("volunteer")
    client.get("/lang/ru")
    r = client.post("/login", data={"email": v["email"], "password": "Wrong12345"}, follow_redirects=True)
    assert "Неверная электронная почта или пароль." in r.get_data(as_text=True)
    client.get("/lang/en")
    r = login(client, v["email"], PASSWORD)
    assert f"Welcome, {v['email'] and 'Тест'}" in r.get_data(as_text=True)


def test_error_pages_are_translated(client):
    client.get("/lang/ru")
    r = client.get("/no-such-page")
    assert r.status_code == 404 and "Страница не найдена" in r.get_data(as_text=True)
    client.get("/lang/en")
    assert "Page not found" in client.get("/no-such-page").get_data(as_text=True)


def test_event_pages_use_language_for_dates_and_cities(make, client):
    org = make.user("organizer")
    ev = make.event(org, city="Қызылорда")
    client.get("/lang/ru")
    body = client.get(f"/events/{ev}").get_data(as_text=True)
    assert "Кызылорда" in body and "Организатор:" in body and "Қызылорда" not in body
    client.get("/lang/en")
    assert "Kyzylorda" in client.get(f"/events/{ev}").get_data(as_text=True)


def test_csv_headers_follow_language(make, client):
    org = make.user("organizer")
    ev = make.event(org)
    login(client, org["email"])
    client.get("/lang/en")
    csv_text = client.get(f"/organizer/events/{ev}/participants.csv").get_data(as_text=True)
    assert csv_text.lstrip("\ufeff").startswith("Volunteer;Email;Registered at")
    client.get("/lang/ru")
    assert "Номер сертификата" in client.get(f"/organizer/events/{ev}/participants.csv").get_data(as_text=True)


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_certificate_pdf_in_each_language(tmp_path, lang):
    out = str(tmp_path / f"{lang}.pdf")
    cs.render_pdf(out, code="VP-2026-TEST", volunteer="Test Volunteer", event_title="Test",
                  event_date="2026-05-01 10:00", issued_at="2026-05-02 10:00", organizer="Org", lang=lang)
    assert Path(out).read_bytes().startswith(b"%PDF")


def test_certificate_download_uses_current_language(app, make, client):
    org, vol = make.user("organizer"), make.user("volunteer")
    ev = make.event(org, days=-3)
    reg = make.registration(vol, ev, status="attended")
    login(client, vol["email"])
    client.get("/lang/en")
    r = client.get(f"/certificates/{reg}/download")
    assert r.status_code == 200 and r.mimetype == "application/pdf"


def test_chart_renders_in_every_language(make, client):
    org = make.user("organizer")
    make.event(org)
    login(client, org["email"])
    for lang in ("kk", "ru", "en"):
        client.get(f"/lang/{lang}")
        r = client.get("/statistics/chart/summary.png")
        assert r.status_code == 200 and r.data.startswith(b"\x89PNG")


# ---------- іздеу барлық тілде ----------

@pytest.mark.parametrize("text", ["экология Кызылорда", "ecology Kyzylorda", "экология Қызылордада"])
def test_search_understands_city_in_any_language(text):
    r = search_service.parse(text, today=date(2026, 11, 18))
    assert r["city"] == "Қызылорда"


@pytest.mark.parametrize("text, label", [("на этой неделе", "осы апта"), ("this week", "осы апта"), ("завтра", "ертең"),
                                          ("today", "бүгін"), ("в этом месяце", "осы ай")])
def test_search_understands_dates_in_any_language(text, label):
    r = search_service.parse(text, today=date(2026, 11, 18))
    assert label in r["labels"] and r["date_from"]
