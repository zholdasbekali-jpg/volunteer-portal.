"""Іс-шаралар каталогы (жария) және ұйымдастырушы панелі."""
import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import CITIES, REG_STATUS_LABELS, ROLE_ADMIN, ROLE_ORGANIZER
from .services import certificate_service, event_service, registration_service, statistics_service

bp = Blueprint("events", __name__)
STATUS_FILTERS = (("", "Барлығы"), ("upcoming", "Алдағы"),
                  ("past", "Өткен"), ("cancelled", "Тоқтатылған"))


@bp.route("/")
def index():
    upcoming, _ = event_service.split_upcoming_past(event_service.search_events())
    return render_template("index.html", upcoming=upcoming[:3],
                           summary=statistics_service.get_summary())


@bp.route("/events")
def catalog():
    q = request.args.get("q", "").strip()
    date = request.args.get("date", "").strip()
    status = request.args.get("status", "").strip()
    city = request.args.get("city", "").strip()
    if city not in CITIES:
        city = ""
    if status not in {s for s, _ in STATUS_FILTERS}:
        status = ""
    events = []
    try:
        events = event_service.search_events(q, date, status, city)
    except ServiceError as exc:
        flash(exc.message, "warning")
    # Сүзгі қолданылмаса — алдағы және өткенді бөлек көрсетеміз
    if status == "":
        upcoming, past = event_service.split_upcoming_past(events)
        groups = [("Алдағы іс-шаралар", upcoming), ("Өткен іс-шаралар", past)]
    else:
        groups = [(dict(STATUS_FILTERS)[status] + " іс-шаралар", events)]
    return render_template("events/list.html", groups=groups, total=len(events),
                           q=q, date=date, status=status, city=city, cities=CITIES,
                           status_filters=STATUS_FILTERS)


@bp.route("/events/<int:event_id>")
def detail(event_id):
    event = event_service.get_event(event_id)
    if event is None:
        abort(404)
    my_reg = None
    if current_user.is_authenticated and current_user.is_volunteer:
        my_reg = registration_service.get_user_registration(current_user.id, event_id)
    can_manage = current_user.is_authenticated and event_service.can_manage(event, current_user)
    return render_template("events/detail.html", event=event, my_reg=my_reg,
                           past=event_service.is_past(event), can_manage=can_manage)


# ---------- Ұйымдастырушы (және әкімші) ----------

@bp.route("/organizer")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def organizer_dashboard():
    events = event_service.list_managed_events(current_user)
    scope = None if current_user.is_admin else current_user.id
    return render_template("organizer/dashboard.html", events=events,
                           summary=statistics_service.get_summary(scope))


@bp.route("/organizer/events/new", methods=["GET", "POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def create():
    form = {}
    if request.method == "POST":
        form = request.form
        try:
            event_id = event_service.create_event(current_user, form)
            flash("Іс-шара сәтті құрылды.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        except ServiceError as exc:
            flash(exc.message, "danger")
    return render_template("organizer/event_form.html", form=form, event=None, cities=CITIES)


@bp.route("/organizer/events/<int:event_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def edit(event_id):
    event = event_service.get_event(event_id)
    if event is None:
        abort(404)
    if not event_service.can_manage(event, current_user):
        abort(403)  # басқа ұйымдастырушының іс-шарасы
    form = {k: event[k] for k in ("title", "description", "city", "location", "capacity")}
    form["event_date"] = event["event_date"].replace(" ", "T")
    if request.method == "POST":
        form = request.form
        try:
            event_service.update_event(current_user, event_id, form)
            flash("Өзгерістер сақталды.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        except ServiceError as exc:
            flash(exc.message, "danger")
    return render_template("organizer/event_form.html", form=form, event=event, cities=CITIES)


def _manage_action(event_id, action, ok_message):
    try:
        result = action(current_user, event_id)
        certificate_service.remove_files(result)
        flash(ok_message, "success")
    except ServiceError as exc:
        if exc.status_code in (403, 404):
            abort(exc.status_code)
        flash(exc.message, "danger")


@bp.route("/organizer/events/<int:event_id>/cancel", methods=["POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def cancel(event_id):
    _manage_action(event_id, event_service.cancel_event, "Іс-шара тоқтатылды.")
    return redirect(request.referrer or url_for("events.organizer_dashboard"))


@bp.route("/organizer/events/<int:event_id>/restore", methods=["POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def restore(event_id):
    _manage_action(event_id, event_service.restore_event, "Іс-шара қайта жарияланды.")
    return redirect(request.referrer or url_for("events.organizer_dashboard"))


@bp.route("/organizer/events/<int:event_id>/delete", methods=["POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def delete(event_id):
    _manage_action(event_id, event_service.delete_event, "Іс-шара жойылды.")
    return redirect(url_for("events.organizer_dashboard"))


@bp.route("/organizer/events/<int:event_id>/participants")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def participants(event_id):
    event = event_service.get_event(event_id)
    if event is None:
        abort(404)
    try:
        regs = registration_service.list_for_event(current_user, event_id)
    except ServiceError as exc:
        abort(exc.status_code)
    return render_template("organizer/participants.html", event=event, regs=regs)


def _csv_safe(value) -> str:
    """Excel формула енгізуінен қорғау: =, +, -, @ белгісімен басталса, алдына ' қойылады."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/organizer/events/<int:event_id>/participants.csv")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def participants_csv(event_id):
    event = event_service.get_event(event_id)
    if event is None:
        abort(404)
    try:
        regs = registration_service.list_for_event(current_user, event_id)
    except ServiceError as exc:
        abort(exc.status_code)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Ерікті", "Email", "Тіркелген уақыты", "Мәртебесі", "Сертификат нөмірі"])
    for r in regs:
        writer.writerow([_csv_safe(r["full_name"]), _csv_safe(r["email"]), r["registered_at"][:16],
                         REG_STATUS_LABELS.get(r["status"], r["status"]), r["certificate_code"] or ""])
    # utf-8-sig: Excel қазақ әріптерін дұрыс ашады
    body = "\ufeff" + buf.getvalue()
    return Response(body, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=participants_{event_id}.csv"})
