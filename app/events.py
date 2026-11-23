"""Іс-шаралар каталогы (жария) және ұйымдастырушы панелі."""
import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import roles_required
from .i18n import translate as _
from .errors import ServiceError
from .models import (CATEGORY_CODES, CITIES, EVENT_CATEGORIES, REG_STATUSES, REG_STATUS_LABELS,
                     ROLE_ADMIN, ROLE_ORGANIZER, ROLE_VOLUNTEER)
from .services import (audit_service, certificate_service, event_service, favorite_service,
                       registration_service, review_service, search_service, statistics_service,
                       waitlist_service)
from .table_tools import EVENT_FILTERS, filter_rows, search_rows, sort_rows

bp = Blueprint("events", __name__)
STATUS_FILTERS = (("", "Барлығы"), ("upcoming", "Алдағы"),
                  ("past", "Өткен"), ("cancelled", "Тоқтатылған"))
EVENT_SORTS = {"date": ("event_date", True), "title": ("title", False),
               "registered": ("registered_count", True), "status": ("status", False)}
PARTICIPANT_SORTS = {"date": ("registered_at", False), "name": ("full_name", False),
                     "status": ("status", False)}


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
    category = request.args.get("category", "").strip()
    if category not in CATEGORY_CODES:
        category = ""
    if status not in {s for s, _ in STATUS_FILTERS}:
        status = ""
    events = []
    try:
        events = event_service.search_events(q, date, status, city, category)
    except ServiceError as exc:
        flash(exc.message, "warning")
    # Сүзгі қолданылмаса — алдағы және өткенді бөлек көрсетеміз
    if status == "":
        upcoming, past = event_service.split_upcoming_past(events)
        groups = [("Алдағы іс-шаралар", upcoming), ("Өткен іс-шаралар", past)]
    else:
        groups = [(dict(STATUS_FILTERS)[status] + " іс-шаралар", events)]
    hints = search_service.parse(q)["labels"] if q else []
    return render_template("events/list.html", groups=groups, total=len(events), hints=hints,
                           q=q, date=date, status=status, city=city, cities=CITIES,
                           category=category, categories=EVENT_CATEGORIES,
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
    wait_position = (waitlist_service.position(current_user.id, event_id)
                     if current_user.is_authenticated and current_user.is_volunteer and my_reg is None else None)
    return render_template("events/detail.html", event=event, my_reg=my_reg,
                           wait_position=wait_position,
                           reviews=review_service.list_for_event(event_id),
                           review_summary=review_service.summary(event_id),
                           can_review=(current_user.is_authenticated
                                       and review_service.can_review(current_user, event_id)),
                           is_favorite=(current_user.is_authenticated and current_user.is_volunteer
                                        and favorite_service.is_favorite(current_user, event_id)),
                           past=event_service.is_past(event), can_manage=can_manage)


@bp.route("/events/<int:event_id>/reviews", methods=["POST"])
@roles_required(ROLE_VOLUNTEER)
def add_review(event_id):
    try:
        review_service.add(current_user, event_id, request.form.get("rating"),
                           request.form.get("comment", ""))
        flash("Пікіріңіз сақталды. Рахмет!", "success")
    except ServiceError as exc:
        if exc.status_code in (403, 404):
            abort(exc.status_code)
        flash(exc.message, "danger")
    return redirect(url_for("events.detail", event_id=event_id))


# ---------- Ұйымдастырушы (және әкімші) ----------

@bp.route("/organizer")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def organizer_dashboard():
    events = event_service.list_managed_events(current_user)
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()
    if category not in CATEGORY_CODES:
        category = ""
    sort = request.args.get("sort", "date")
    events = search_rows(events, q, ("title", "city", "location", "organizer_name"))
    if status in ("upcoming", "past"):
        upcoming, past = event_service.split_upcoming_past(events)
        events = upcoming if status == "upcoming" else past
    elif status in ("published", "cancelled"):
        events = filter_rows(events, "status", status)
    else:
        status = ""
    events = filter_rows(events, "category", category)
    events = sort_rows(events, sort, EVENT_SORTS, "date")
    scope = None if current_user.is_admin else current_user.id
    return render_template("organizer/dashboard.html", events=events,
                           summary=statistics_service.get_summary(scope),
                           status_filters=EVENT_FILTERS, categories=EVENT_CATEGORIES,
                           f={"q": q, "status": status, "category": category,
                              "sort": sort if sort in EVENT_SORTS else "date"})


@bp.route("/organizer/events/new", methods=["GET", "POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def create():
    form = {}
    if request.method == "POST":
        form = request.form
        try:
            event_id = event_service.create_event(current_user, form)
            if current_user.is_admin:
                audit_service.log(current_user, "event.created", "event", event_id,
                                  f"event_id={event_id}")
            flash("Іс-шара сәтті құрылды.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        except ServiceError as exc:
            flash(exc.message, "danger")
    return render_template("organizer/event_form.html", form=form, event=None, cities=CITIES,
                           categories=EVENT_CATEGORIES)


@bp.route("/organizer/events/<int:event_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def edit(event_id):
    event = event_service.get_event(event_id)
    if event is None:
        abort(404)
    if not event_service.can_manage(event, current_user):
        abort(403)  # басқа ұйымдастырушының іс-шарасы
    fields = ("title", "description", "city", "location", "capacity", "hours", "category")
    form = {k: event[k] for k in fields}
    form["event_date"] = event["event_date"].replace(" ", "T")
    if request.method == "POST":
        form = request.form
        try:
            event_service.update_event(current_user, event_id, form)
            if current_user.is_admin:
                audit_service.log(current_user, "event.updated", "event", event_id,
                                  f"event_id={event_id}")
            flash("Өзгерістер сақталды.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        except ServiceError as exc:
            flash(exc.message, "danger")
    return render_template("organizer/event_form.html", form=form, event=event, cities=CITIES,
                           categories=EVENT_CATEGORIES)


def _manage_action(event_id, action, ok_message):
    try:
        result = action(current_user, event_id)
        certificate_service.remove_files(result)
        codes = {"cancel_event": "event.cancelled", "restore_event": "event.restored",
                 "delete_event": "event.deleted"}
        if current_user.is_admin and action.__name__ in codes:
            audit_service.log(current_user, codes[action.__name__], "event", event_id,
                              f"event_id={event_id}")
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
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", "date")
    regs = search_rows(regs, q, ("full_name", "email", "certificate_code"))
    if status not in REG_STATUS_LABELS:
        status = ""
    regs = sort_rows(filter_rows(regs, "status", status), sort, PARTICIPANT_SORTS, "date")
    try:
        waiting = waitlist_service.list_for_event(current_user, event_id)
    except ServiceError as exc:
        abort(exc.status_code)
    return render_template("organizer/participants.html", event=event, regs=regs, waiting=waiting,
                           reg_statuses=list(REG_STATUS_LABELS.items()),
                           f={"q": q, "status": status,
                              "sort": sort if sort in PARTICIPANT_SORTS else "date"})


@bp.route("/organizer/events/<int:event_id>/participants/status", methods=["POST"])
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def bulk_participant_status(event_id):
    """Массовое изменение посещаемости: только участники events, доступные актору."""
    try:
        allowed = {r["id"] for r in registration_service.list_for_event(current_user, event_id)}
    except ServiceError as exc:
        abort(exc.status_code)
    status = request.form.get("status", "")
    ids = [int(v) for v in request.form.getlist("ids") if v.isdigit()]
    if any(rid not in allowed for rid in ids):
        abort(403)  # тек осы іс-шараның тіркелімдерін өзгертуге болады
    if status not in REG_STATUSES:
        flash("Белгісіз қатысу мәртебесі.", "danger")
    elif not ids:
        flash("Ештеңе таңдалмады.", "warning")
    else:
        removed = []
        try:
            for rid in ids:
                removed += registration_service.set_attendance(current_user, rid, status)
            certificate_service.remove_files(removed)
            flash("Таңдалған тіркелімдер жаңартылды.", "success")
        except ServiceError as exc:
            if exc.status_code in (403, 404):
                abort(exc.status_code)
            flash(exc.message, "danger")
    args = {key: value for key, value in (
        ("q", request.form.get("q", "")),
        ("status", request.form.get("filter_status", "")),
        ("sort", request.form.get("sort", "")),
    ) if value}
    return redirect(url_for("events.participants", event_id=event_id, **args))


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
    writer.writerow([_(h) for h in ("Ерікті", "Email", "Тіркелген уақыты", "Мәртебесі", "Сертификат нөмірі")])
    for r in regs:
        writer.writerow([_csv_safe(r["full_name"]), _csv_safe(r["email"]), r["registered_at"][:16],
                         _(REG_STATUS_LABELS.get(r["status"], r["status"])), r["certificate_code"] or ""])
    # utf-8-sig: Excel қазақ әріптерін дұрыс ашады
    body = "\ufeff" + buf.getvalue()
    return Response(body, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=participants_{event_id}.csv"})
