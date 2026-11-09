"""CSRF-қорғаныс және қауіпсіз қайта бағыттау көмекшілері."""
import hmac
import secrets
from urllib.parse import urlparse

from flask import abort, current_app, request, session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_csrf_token() -> str:
    """Сессияға байланған кездейсоқ токен (бірінші сұрауда жасалады)."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def csrf_protect() -> None:
    """before_request: өзгертетін әрекеттерде токенді тексереді, әйтпесе 400."""
    if not current_app.config.get("CSRF_ENABLED", True) or request.method in SAFE_METHODS:
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
    expected = session.get("_csrf_token", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="CSRF токені жарамсыз немесе мерзімі өткен. Бетті жаңартып, қайталаңыз.")


def is_safe_next(target: str) -> bool:
    """Тек сайт ішіндегі салыстырмалы жолға қайта бағыттауға рұқсат (open redirect жоқ)."""
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/") and not target.startswith("//")
