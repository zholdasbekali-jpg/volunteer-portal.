"""Авторизация маршруттары: тіркелу, кіру, шығу + рөлдерді сервер жағында тексеру."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from . import i18n
from .errors import ServiceError, TooManyAttempts
from .models import (APPROVAL_APPROVED, ROLE_ORGANIZER, ROLE_VOLUNTEER, User, approval_of)
from .security import is_safe_next
from .services import auth_service, throttle_service

bp = Blueprint("auth", __name__)


def roles_required(*roles):
    """Рөлді серверде тексереді: кірмеген — кіру бетіне, рөлі сәйкес емес — 403.
    Батырманы интерфейстен жасыру қорғаныс болып саналмайды, нақты тосқауыл осы жерде."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            # Мақұлданбаған ұйымдастырушы жүйеге кіре алады, бірақ іс-шараларды басқара алмайды.
            if current_user.role == ROLE_ORGANIZER and approval_of(current_user) != APPROVAL_APPROVED:
                return redirect(url_for("auth.pending_approval"))
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
        if approval_of(user) != APPROVAL_APPROVED:
            return url_for("auth.pending_approval")
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
        email, ip = form.get("email", ""), request.remote_addr
        try:
            throttle_service.check(email, ip)
            try:
                row = auth_service.authenticate(email, form.get("password"))
            except ServiceError:
                throttle_service.record_failure(email, ip)
                raise
            throttle_service.reset(email)
            user = User(row)
            chosen = session.get("lang")
            session.clear()          # session fixation-ге қарсы: кіргенде сессия жаңартылады
            lang = chosen if chosen in i18n.CODES else (row["lang"] if row["lang"] in i18n.CODES else None)
            if lang:                 # бұрын таңдалған тіл (немесе профильдегі) сақталады
                session["lang"] = lang
                if lang != row["lang"]:
                    auth_service.set_user_lang(row["id"], lang)
            login_user(user)
            flash(f"Қош келдіңіз, {user.full_name}!", "success")
            nxt = request.args.get("next", "")
            return redirect(nxt if is_safe_next(nxt) else home_for(user))
        except ServiceError as exc:
            flash(exc.message, "danger")
            if isinstance(exc, TooManyAttempts):
                return render_template("auth/login.html", form=form), 429
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Сіз жүйеден шықтыңыз.", "info")
    return redirect(url_for("events.index"))


@bp.route("/pending-approval")
@login_required
def pending_approval():
    """Мақұлдауды күтіп тұрған (немесе қабылданбаған) ұйымдастырушыға арналған бет."""
    if current_user.role != ROLE_ORGANIZER or approval_of(current_user) == APPROVAL_APPROVED:
        return redirect(home_for(current_user))
    return render_template("auth/pending_approval.html", approval=approval_of(current_user))
