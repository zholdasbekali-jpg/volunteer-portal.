"""Авторизация маршруттары: тіркелу, кіру, шығу + рөлдерді сервер жағында тексеру."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .errors import ServiceError
from .models import ROLE_ORGANIZER, ROLE_VOLUNTEER, User
from .security import is_safe_next
from .services import auth_service

bp = Blueprint("auth", __name__)


def roles_required(*roles):
    """Рөлді серверде тексереді: кірмеген — кіру бетіне, рөлі сәйкес емес — 403.
    Батырманы интерфейстен жасыру қорғаныс болып саналмайды, нақты тосқауыл осы жерде."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def home_for(user) -> str:
    """Кіргеннен кейінгі әдепкі бет рөлге байланысты."""
    if user.is_admin:
        return url_for("admin.dashboard")
    if user.is_organizer:
        return url_for("events.organizer_dashboard")
    return url_for("registrations.my_registrations")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    form = {}
    if request.method == "POST":
        form = request.form
        role = form.get("role", ROLE_VOLUNTEER)
        try:
            auth_service.register_user(form.get("full_name"), form.get("email"),
                                       form.get("password"), role)
            flash("Тіркелу сәтті аяқталды! Енді жүйеге кіріңіз.", "success")
            return redirect(url_for("auth.login"))
        except ServiceError as exc:
            flash(exc.message, "danger")
    return render_template("auth/register.html", form=form,
                           roles=((ROLE_VOLUNTEER, "Ерікті"), (ROLE_ORGANIZER, "Ұйымдастырушы")))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    form = {}
    if request.method == "POST":
        form = request.form
        try:
            row = auth_service.authenticate(form.get("email"), form.get("password"))
            user = User(row)
            login_user(user)
            flash(f"Қош келдіңіз, {user.full_name}!", "success")
            nxt = request.args.get("next", "")
            return redirect(nxt if is_safe_next(nxt) else home_for(user))
        except ServiceError as exc:
            flash(exc.message, "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Сіз жүйеден шықтыңыз.", "info")
    return redirect(url_for("events.index"))
