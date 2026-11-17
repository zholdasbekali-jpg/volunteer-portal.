"""Сертификат беті, PDF жүктеу және түпнұсқалығын тексеру."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import ROLE_VOLUNTEER
from .services import certificate_service, checkin_service

bp = Blueprint("certificates", __name__)


@bp.route("/certificates")
@roles_required(ROLE_VOLUNTEER)
def list_certificates():
    return render_template("certificates/list.html",
                           items=certificate_service.list_available(current_user.id))


@bp.route("/certificates/<int:registration_id>/download")
@roles_required(ROLE_VOLUNTEER)
def download(registration_id):
    try:
        # QR-дағы сілтеме: PUBLIC_URL (баптауда) немесе сұрау келген мекенжай
        base = current_app.config.get("PUBLIC_URL") or request.url_root
        cert = certificate_service.issue_certificate(current_user, registration_id, base)
    except ServiceError as exc:
        # Басқа біреудің немесе қатыспаған тіркелімі: 403/404/409 -> түсінікті бет
        abort(exc.status_code if exc.status_code in (403, 404) else 403)
    return send_file(cert["pdf_path"], mimetype="application/pdf", as_attachment=True,
                     download_name=f"{cert['certificate_code']}.pdf")


@bp.route("/verify")
def scan():
    """Сканер беті. ?code=<мәтін> келсе (QR мазмұны немесе қолмен енгізілген), нөмірді алып тексеру бетіне өтеді."""
    raw = request.args.get("code", "").strip()
    if raw:
        # Іс-шарадағы «қатысуды белгілеу» QR-ы да осы сканерде танылады
        token = checkin_service.extract_token(raw[:300]) if "/checkin/" in raw else None
        if token:
            return redirect(url_for("checkin.confirm", token=token))
        code = certificate_service.extract_code(raw[:300])
        if code:
            return redirect(url_for("certificates.verify", code=code))
        flash("Сертификат нөмірі табылмады. Нөмір мына түрде болуы керек: VP-2026-1A2B3C4D.", "warning")
    return render_template("certificates/scan.html")


@bp.route("/verify/<code>")
def verify(code):
    cert = certificate_service.verify(code)
    return render_template("certificates/verify.html", cert=cert, code=code)
