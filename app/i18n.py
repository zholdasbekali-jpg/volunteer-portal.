"""Көптілділік: қазақша / орысша / ағылшынша.

Қазақша мәтіннің өзі кілт болып саналады (әдепкі тіл), сондықтан kk үшін аударма файлы керек емес.
ru мен en аудармалары app/translations/<тіл>.json ішінде: {"қазақша мәтін": "аударма"}.
Параметрлі жолдар: «Қош келдіңіз, {name}!». Дайын пішімделген хабарламаны (мыс. flash) да аударады:
«{name}» үлгісіне сәйкес келсе, мәндерді аударманың ішіне қояды.
"""
import json
import re
from pathlib import Path

from flask import Blueprint, abort, has_request_context, redirect, request, session, url_for
from flask_login import current_user

from .models import DEFAULT_LANG, LANG_CODES as CODES
from .security import is_safe_next

LANGS = (("kk", "Қазақша"), ("ru", "Русский"), ("en", "English"))

_DIR = Path(__file__).resolve().parent / "translations"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_catalogs: dict = {}

bp = Blueprint("i18n", __name__)


def _catalog(lang: str) -> dict:
    """{'exact': {...}, 'patterns': [(regex, шаблон)]} — файлдан бір рет оқылады."""
    if lang not in _catalogs:
        path = _DIR / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        patterns = []
        for key, value in data.items():
            if _PLACEHOLDER.search(key):
                rx = re.escape(key)
                rx = _PLACEHOLDER.sub(lambda m: f"(?P<{m.group(1)}>.+?)", rx.replace(r"\{", "{").replace(r"\}", "}"))
                patterns.append((re.compile(rx, re.DOTALL), value))
        _catalogs[lang] = {"exact": data, "patterns": patterns}
    return _catalogs[lang]


def current_lang() -> str:
    """Ағымдағы сұраудың тілі (сессияда сақталған); сұраудан тыс немесе таңдалмаса — әдепкі қазақша."""
    if has_request_context():
        lang = session.get("lang")
        if lang in CODES:
            return lang
    return DEFAULT_LANG


def translate(text, lang: str | None = None, **params) -> str:
    """Мәтінді ағымдағы тілге аударады. Аударма табылмаса, қазақша түпнұсқа қайтады.
    params берілсе, {атау} орындарына мәндер қойылады."""
    if not text:
        return text or ""
    lang = lang or current_lang()
    result = text
    if lang != DEFAULT_LANG:
        cat = _catalog(lang)
        found = cat["exact"].get(text)
        if found is not None:
            result = found
        else:
            for rx, template in cat["patterns"]:
                m = rx.fullmatch(text)
                if m:
                    # мәндер (мыс. қала атауы) бар болса, өздері де аударылады
                    values = {k: cat["exact"].get(v, v) for k, v in m.groupdict().items()}
                    return _PLACEHOLDER.sub(lambda g: str(values[g.group(1)]), template)
    return _PLACEHOLDER.sub(lambda g: str(params[g.group(1)]) if g.group(1) in params else g.group(0),
                            result) if params else result


MONTHS = {
    "kk": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
           "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
}


def format_date(value: str, with_time: bool = True, lang: str | None = None) -> str:
    """'2026-05-01 10:00' -> '1 мамыр 2026, 10:00' / '1 мая 2026, 10:00' / '1 May 2026, 10:00'."""
    if not value:
        return ""
    lang = lang if lang in CODES else current_lang()
    y, m, d = int(value[:4]), int(value[5:7]), int(value[8:10])
    text = f"{d} {MONTHS[lang][m - 1]} {y}"
    return f"{text}, {value[11:16]}" if with_time and len(value) >= 16 else text


def context() -> dict:
    """Барлық шаблонға: ағымдағы тіл коды және ауыстырғыш үшін тілдер тізімі."""
    return {"lang": current_lang(), "LANGS": LANGS}


@bp.route("/lang/<code>")
def set_language(code):
    """Тілді ауыстырады (сессияда, кірген болса — профильде де) да сол бетке қайтарады."""
    if code not in CODES:
        abort(404)
    session["lang"] = code
    if current_user.is_authenticated:
        from .services import auth_service
        auth_service.set_user_lang(current_user.id, code)
    nxt = request.args.get("next", "")
    return redirect(nxt if is_safe_next(nxt) else url_for("events.index"))
