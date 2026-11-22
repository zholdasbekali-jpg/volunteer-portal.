"""Volunteer ID (жеке карточка, жария бет) және рейтинг."""
from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required

from .checkin import _qr_svg
from .errors import NotFound
from .models import ROLE_VOLUNTEER
from .services import rating_service, volunteer_service

bp = Blueprint("volunteers", __name__)


def _public_url(code: str) -> str:
    base = current_app.config.get("PUBLIC_URL") or request.url_root
    return f"{base.rstrip('/')}/id/{code}"


@bp.route("/cabinet/id")
@login_required
def my_card():
    if current_user["role"] != ROLE_VOLUNTEER:
        flash("Volunteer ID тек еріктілерге беріледі.", "info")
        return redirect(url_for("cabinet.index"))
    card = volunteer_service.get_own_card(current_user)
    return render_template("volunteer/id_card.html", card=card, own=True,
                           public_url=_public_url(card["code"]))


@bp.route("/cabinet/id/visibility", methods=["POST"])
@login_required
def visibility():
    if current_user["role"] != ROLE_VOLUNTEER:
        abort(403)
    make_public = request.form.get("public") == "1"
    volunteer_service.set_public(current_user, make_public)
    flash("Профиль жария." if make_public else "Профиль жабылды: ID беті аты-жөнін көрсетпейді.", "success")
    return redirect(url_for("volunteers.my_card"))


@bp.route("/id/<code>")
def public_card(code):
    try:
        card = volunteer_service.get_public_card(code)
    except NotFound:
        abort(404)
    return render_template("volunteer/id_card.html", card=card, own=False,
                           public_url=_public_url(card["code"]))


@bp.route("/id/<code>/qr.svg")
def qr(code):
    try:
        card = volunteer_service.get_public_card(code)
    except NotFound:
        abort(404)
    return Response(_qr_svg(_public_url(card["code"])), mimetype="image/svg+xml")


@bp.route("/rating")
def rating():
    period = rating_service.normalize_period(request.args.get("period", ""))
    return render_template("rating.html", period=period, periods=rating_service.PERIODS,
                           volunteers=rating_service.top_volunteers(period),
                           organizers=rating_service.top_organizers(period),
                           cities=rating_service.top_cities(period))
