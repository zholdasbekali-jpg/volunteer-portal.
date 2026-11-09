"""Тіркелу, бас тарту, эріктінің жеке кабинеті, қатысуды белгілеу."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import REG_ABSENT, REG_ATTENDED, REG_PENDING, ROLE_ADMIN, ROLE_ORGANIZER, ROLE_VOLUNTEER
from .services import certificate_service, event_service, registration_service

bp = Blueprint("registrations", __name__)


@bp.route("/events/<int:event_id>/register", methods=["POST"])
@roles_required(ROLE_VOLUNTEER)
def register(event_id):
    try:
        registration_service.register(current_user, event_id)
        flash("Сіз іс-шараға сәтті тіркелдіңіз!", "success")
    except ServiceError as exc:
        if exc.status_code == 404:
            abort(404)
        flash(exc.message, "danger")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/my")
@roles_required(ROLE_VOLUNTEER)
def my_registrations():
    regs = registration_service.list_for_user(current_user.id)
    return render_template("volunteer/dashboard.html", regs=regs, now_str=event_service.now_str())


@bp.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
@roles_required(ROLE_VOLUNTEER)
def cancel(registration_id):
    try:
        registration_service.cancel_registration(current_user, registration_id)
        flash("Тіркелуден бас тарттыңыз, орын босатылды.", "info")
    except ServiceError as exc:
        if exc.status_code in (403, 404):
            abort(exc.status_code)
        flash(exc.message, "danger")
    return redirect(url_for("registrations.my_registrations"))


@bp.route("/registrations/<int:registration_id>/status", methods=["POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def set_status(registration_id):
    status = request.form.get("status", "")
    event_id = request.form.get("event_id", type=int)
    try:
        removed = registration_service.set_attendance(current_user, registration_id, status)
        certificate_service.remove_files(removed)
        flash("Қатысу мәртебесі жаңартылды.", "success")
    except ServiceError as exc:
        if exc.status_code in (403, 404):
            abort(exc.status_code)
        flash(exc.message, "danger")
    if event_id:
        return redirect(url_for("events.participants", event_id=event_id))
    return redirect(url_for("events.organizer_dashboard"))
