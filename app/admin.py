"""Әкімші панелі: пайдаланушылар, іс-шаралар, тіркелімдер, жалпы статистика."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import ROLES, ROLE_ADMIN, ROLE_LABELS
from .services import auth_service, certificate_service, event_service, registration_service, statistics_service

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@roles_required(ROLE_ADMIN)
def dashboard():
    return render_template(
        "admin/dashboard.html",
        summary=statistics_service.get_summary(),
        users=auth_service.list_users(),
        events=event_service.list_managed_events(current_user),
        regs=registration_service.list_all(current_user),
        roles=[(r, ROLE_LABELS[r]) for r in ROLES],
    )


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@roles_required(ROLE_ADMIN)
def change_role(user_id):
    try:
        auth_service.set_user_role(current_user, user_id, request.form.get("role", ""))
        flash("Пайдаланушы рөлі өзгертілді.", "success")
    except ServiceError as exc:
        if exc.status_code == 404:
            abort(404)
        flash(exc.message, "danger")
    return redirect(url_for("admin.dashboard") + "#users")


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@roles_required(ROLE_ADMIN)
def delete_user(user_id):
    try:
        paths = auth_service.delete_user(current_user, user_id)
        certificate_service.remove_files(paths)
        flash("Пайдаланушы жойылды.", "success")
    except ServiceError as exc:
        if exc.status_code == 404:
            abort(404)
        flash(exc.message, "danger")
    return redirect(url_for("admin.dashboard") + "#users")
