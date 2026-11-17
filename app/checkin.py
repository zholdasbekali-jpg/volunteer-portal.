"""QR арқылы қатысуды өзі белгілеу: ұйымдастырушы экраны және ерікті растау беті."""
from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from .auth import roles_required
from .errors import ServiceError
from .models import ROLE_ADMIN, ROLE_ORGANIZER, ROLE_VOLUNTEER
from .services import checkin_service

bp = Blueprint("checkin", __name__)


def _qr_svg(text: str, size: int = 360) -> str:
    widget = QrCodeWidget(text, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    return renderSVG.drawToString(drawing)


def _guard(event_id):
    """Тек өз іс-шарасының (немесе әкімші) санауын береді; әйтпесе 403/404."""
    try:
        return checkin_service.attendance_counts(current_user, event_id)
    except ServiceError as exc:
        abort(exc.status_code if exc.status_code in (403, 404) else 403)


@bp.route("/organizer/events/<int:event_id>/checkin")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def screen(event_id):
    info = _guard(event_id)
    return render_template("organizer/checkin.html", event=info["event"], total=info["total"],
                           attended=info["attended"], step=checkin_service.STEP_SECONDS)


@bp.route("/organizer/events/<int:event_id>/checkin/qr.svg")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def qr_svg(event_id):
    _guard(event_id)
    base = current_app.config.get("PUBLIC_URL") or request.url_root
    url = f"{base.rstrip('/')}/checkin/{checkin_service.make_token(event_id)}"
    return Response(_qr_svg(url), mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@bp.route("/organizer/events/<int:event_id>/checkin/stats")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def stats(event_id):
    info = _guard(event_id)
    return jsonify(total=info["total"], attended=info["attended"]), 200, {"Cache-Control": "no-store"}


@bp.route("/checkin/<token>", methods=["GET", "POST"])
@login_required
def confirm(token):
    """GET: растау беті (деректі өзгертпейді). POST: CSRF-пен қорғалған белгілеу."""
    if current_user["role"] != ROLE_VOLUNTEER:
        abort(403)
    if request.method == "POST":
        try:
            result = checkin_service.check_in(current_user, token)
        except ServiceError as exc:
            flash(exc.message, "danger")
            return redirect(url_for("checkin.confirm", token=token))
        flash("Қатысуыңыз белгіленді! Сертификатты «Сертификаттар» бөлімінен жүктей аласыз."
              if not result["already"] else "Қатысуыңыз бұрын белгіленген.", "success")
        return redirect(url_for("registrations.my_registrations"))
    try:
        event = checkin_service.get_event_for_token(token)
    except ServiceError as exc:
        return render_template("volunteer/checkin_confirm.html", event=None, error=exc.message, token=token), 400
    return render_template("volunteer/checkin_confirm.html", event=event, error=None, token=token)
