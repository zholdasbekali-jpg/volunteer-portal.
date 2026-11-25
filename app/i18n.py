"""Үш тілді интерфейс: қазақша (негізгі), орысша, ағылшынша.

Бастапқы мәтін қазақша: каталог кілті — дәл сол қазақша жол. Қазақша үшін ештеңе аударылмайды.
Формат-жолдар үшін ({0}, {1}) кілттері үлгі ретінде салыстырылады.
Шаблондарда: {{ _('қазақша мәтін') }}; серверден келген мәтін (flash, қате, қала, мәртебе) де {{ _(айнымалы) }} арқылы.
Пайдаланушы енгізген деректер (атау, сипаттама, аты-жөні) ешқашан аударылмайды."""
import json
import re
from pathlib import Path

from flask import g, has_request_context, request

LANGS = (("kk", "Қазақша", "ҚАЗ"), ("ru", "Русский", "РУС"), ("en", "English", "ENG"))
CODES = tuple(c for c, _, _ in LANGS)
DEFAULT = "kk"
COOKIE = "lang"
_DIR = Path(__file__).parent / "translations"
_PLACEHOLDER = re.compile(r"\{(\d+)\}")

MONTHS = {
    "kk": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз",
           "қыркүйек", "қазан", "қараша", "желтоқсан"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}


class Translated(str):
    """Аударылған жол (белгі)."""


_catalogs = {}
_patterns = {}


def _load(lang: str) -> dict:
    if lang not in _catalogs:
        path = _DIR / f"{lang}.json"
        _catalogs[lang] = json.loads(path.read_text(encoding="utf8")) if path.exists() else {}
        pats = []
        for key, value in _catalogs[lang].items():
            if _PLACEHOLDER.search(key):
                regex = "".join(f"(.+?)" if i % 2 else re.escape(part)
                                for i, part in enumerate(_PLACEHOLDER.split(key)))
                order = [int(n) for n in _PLACEHOLDER.findall(key)]
                pats.append((re.compile(regex + r"\Z", re.S), order, value))
        _patterns[lang] = pats
    return _catalogs[lang]


def reload() -> None:
    _catalogs.clear()
    _patterns.clear()


def detect_lang() -> str:
    """Cookie -> Accept-Language -> қазақша."""
    code = request.cookies.get(COOKIE, "")
    if code in CODES:
        return code
    best = request.accept_languages.best_match(CODES)
    return best or DEFAULT


def get_lang() -> str:
    if not has_request_context():
        return DEFAULT
    lang = g.get("lang")
    if lang is None:
        lang = g.lang = detect_lang()
    return lang


def translate(text: str, lang: str) -> str:
    if lang == DEFAULT or not text:
        return text
    cat = _load(lang)
    hit = cat.get(text)
    if hit is not None:
        return hit
    if len(text) <= 300:
        for regex, order, value in _patterns[lang]:
            m = regex.match(text)
            if m:
                parts = [translate(x, lang) for x in m.groups()]
                try:
                    return value.format(*parts)
                except (IndexError, KeyError):
                    return text
    return text


def tr(text, lang: str = None):
    """Мәтінді ағымдағы (немесе берілген) тілге аударады; табылмаса, түпнұсқа қайтады."""
    if not isinstance(text, str):
        return text
    return Translated(translate(text, lang or get_lang()))


def gettext(text: str, *args):
    out = tr(text)
    return Translated(out.format(*args)) if args else out


def format_date(value: str, with_time: bool = True) -> str:
    """'2026-05-01 10:00' -> '1 мамыр 2026, 10:00' / '1 мая 2026, 10:00' / '1 May 2026, 10:00'."""
    if not value:
        return ""
    y, m, d = int(value[:4]), int(value[5:7]), int(value[8:10])
    text = f"{d} {MONTHS[get_lang()][m - 1]} {y}"
    return f"{text}, {value[11:16]}" if with_time and len(value) >= 16 else text


def js_strings() -> dict:
    """Браузер скрипттеріне керекті хабарлар (CSP-ге байланысты, inline-скрипт жоқ)."""
    keys = {
        "chart_error": "График жүктелмеді. Бетті жаңартып көріңіз.",
        "camera_denied": "Камераға рұқсат берілмеді немесе камера табылмады. Фотоны жүктеңіз немесе нөмірді қолмен енгізіңіз.",
        "no_qr": "Суреттен QR-код табылмады. Анығырақ, жақынырақ түсіріп көріңіз немесе нөмірді қолмен енгізіңіз.",
        "image_error": "Суретті оқу мүмкін болмады.",
    }
    return {k: tr(v) for k, v in keys.items()}


class LabelDict(dict):
    """{код: қазақша атау}; оқығанда ағымдағы тілге аударады (шаблондарда ROLE_LABELS[x])."""

    def __getitem__(self, key):
        return tr(super().__getitem__(key))

    def get(self, key, default=None):
        return tr(super().get(key, default))


def safe_back(target: str, host: str) -> str:
    """Тілді ауыстырғаннан кейін қайтатын жер: тек осы сайттың ішкі жолы."""
    from urllib.parse import urlsplit
    if not target:
        return "/"
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        if parts.netloc != host or parts.scheme not in ("http", "https"):
            return "/"
        target = parts.path + (f"?{parts.query}" if parts.query else "")
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target
