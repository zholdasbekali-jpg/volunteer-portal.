"""Сертификат беті, PDF жүктеу және түпнұсқалығын тексеру."""
from flask import Blueprint, abort, render_template, send_file
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import ROLE_VOLUNTEER
from .services import certificate_service

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
        cert = certificate_service.issue_certificate(current_user, registration_id)
    except ServiceError as exc:
        # Басқа біреудің немесе қатыспаған тіркелімі: 403/404/409 -> түсінікті бет
        abort(exc.status_code if exc.status_code in (403, 404) else 403)
    return send_file(cert["pdf_path"], mimetype="application/pdf", as_attachment=True,
                     download_name=f"{cert['certificate_code']}.pdf")


@bp.route("/verify/<code>")
def verify(code):
    cert = certificate_service.verify(code)
    return render_template("certificates/verify.html", cert=cert, code=code)
