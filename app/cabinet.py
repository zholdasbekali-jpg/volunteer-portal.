"""Жеке кабинет: барлық рөл үшін (ерікті, ұйымдастырушы, әкімші)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .errors import ServiceError
from .services import profile_service

bp = Blueprint("cabinet", __name__, url_prefix="/cabinet")


@bp.route("/")
@login_required
def index():
    return render_template("cabinet/index.html", profile=profile_service.get_profile(current_user),
                           summary=profile_service.cabinet_summary(current_user))


@bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    try:
        profile_service.update_name(current_user, request.form.get("full_name"))
        flash("Аты-жөні жаңартылды.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return redirect(url_for("cabinet.index"))


@bp.route("/password", methods=["POST"])
@login_required
def change_password():
    try:
        profile_service.change_password(current_user, request.form.get("current_password"),
                                        request.form.get("new_password"), request.form.get("confirm_password"))
        flash("Құпиясөз өзгертілді.", "success")
    except ServiceError as exc:
        flash(exc.message, "danger")
    return redirect(url_for("cabinet.index"))
