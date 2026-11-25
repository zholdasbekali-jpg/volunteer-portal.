"""Тілді ауыстыру: /lang/<kk|ru|en> -> cookie және сол бетке қайту."""
from flask import Blueprint, abort, current_app, redirect, request

from . import i18n

bp = Blueprint("language", __name__)


@bp.route("/lang/<code>")
def switch(code):
    if code not in i18n.CODES:
        abort(404)
    resp = redirect(i18n.safe_back(request.args.get("next") or request.referrer or "", request.host))
    resp.set_cookie(i18n.COOKIE, code, max_age=365 * 24 * 3600, samesite="Lax", httponly=True,
                    secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    resp.headers["Cache-Control"] = "no-store"
    return resp
