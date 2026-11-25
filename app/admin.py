"""Әкімші панелі: пайдаланушылар, іс-шаралар, тіркелімдер, жалпы статистика."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import (APPROVAL_APPROVED, APPROVAL_LABELS, APPROVAL_STATUSES, CATEGORY_CODES, EVENT_CATEGORIES,
                     EVENT_STATUS_LABELS, REG_STATUS_LABELS, ROLES, ROLE_ADMIN, ROLE_LABELS,
                     ROLE_ORGANIZER)
from .services import (audit_service, auth_service, certificate_service, event_service,
                       mail_service, registration_service, statistics_service)
from .services.audit_service import AUDIT_ACTIONS
from .table_tools import EVENT_FILTERS, filter_rows, search_rows, sort_rows

bp = Blueprint("admin", __name__, url_prefix="/admin")

TABS = ("users", "events", "regs", "audit")
USER_SORTS = {"id": ("id", False), "name": ("full_name", False),
              "date": ("created_at", True), "role": ("role", False)}
EVENT_SORTS = {"date": ("event_date", True), "title": ("title", False),
               "registered": ("registered_count", True), "status": ("status", False)}
REG_SORTS = {"id": ("id", True), "name": ("full_name", False),
             "date": ("registered_at", True), "status": ("status", False)}


@bp.route("/")
@roles_required(ROLE_ADMIN)
def dashboard():
    tab = request.args.get("tab", "users")
    if tab not in TABS:
        tab = "users"

    users = auth_service.list_users()
    u_q = request.args.get("u_q", "").strip()
    u_role = request.args.get("u_role", "").strip()
    u_approval = request.args.get("u_approval", "").strip()
    u_sort = request.args.get("u_sort", "id")
    if u_role not in ROLES:
        u_role = ""
    if u_approval not in APPROVAL_STATUSES:
        u_approval = ""
    users = sort_rows(
        filter_rows(filter_rows(search_rows(users, u_q, ("full_name", "email")),
                                "role", u_role), "approval", u_approval),
        u_sort, USER_SORTS, "id")

    events = event_service.list_managed_events(current_user)
    e_q = request.args.get("e_q", "").strip()
    e_status = request.args.get("e_status", "").strip()
    e_category = request.args.get("e_category", "").strip()
    if e_category not in CATEGORY_CODES:
        e_category = ""
    e_sort = request.args.get("e_sort", "date")
    events = search_rows(events, e_q, ("title", "organizer_name", "city", "location"))
    if e_status in ("upcoming", "past"):
        upcoming, past = event_service.split_upcoming_past(events)
        events = upcoming if e_status == "upcoming" else past
    elif e_status in EVENT_STATUS_LABELS:
        events = filter_rows(events, "status", e_status)
    else:
        e_status = ""
    events = filter_rows(events, "category", e_category)
    events = sort_rows(events, e_sort, EVENT_SORTS, "date")

    regs = registration_service.list_all(current_user)
    r_q = request.args.get("r_q", "").strip()
    r_status = request.args.get("r_status", "").strip()
    r_sort = request.args.get("r_sort", "id")
    if r_status not in REG_STATUS_LABELS:
        r_status = ""
    regs = sort_rows(filter_rows(search_rows(regs, r_q, ("full_name", "email", "title")),
                                 "status", r_status), r_sort, REG_SORTS, "id")

    a_q = request.args.get("a_q", "").strip()
    a_action = request.args.get("a_action", "").strip()
    audit = audit_service.list_recent(a_q, a_action) if tab == "audit" else []

    filters = {"u_q": u_q, "u_role": u_role, "u_approval": u_approval,
               "u_sort": u_sort if u_sort in USER_SORTS else "id",
               "e_q": e_q, "e_status": e_status, "e_category": e_category,
               "e_sort": e_sort if e_sort in EVENT_SORTS else "date",
               "r_q": r_q, "r_status": r_status, "r_sort": r_sort if r_sort in REG_SORTS else "id",
               "a_q": a_q, "a_action": a_action}
    return render_template(
        "admin/dashboard.html",
        summary=statistics_service.get_summary(),
        users=users, events=events, regs=regs,
        roles=[(r, ROLE_LABELS[r]) for r in ROLES],
        approvals=[(v, APPROVAL_LABELS[v]) for v in APPROVAL_STATUSES],
        approval_labels=APPROVAL_LABELS,
        organizer_role=ROLE_ORGANIZER,
        status_filters=EVENT_FILTERS, categories=EVENT_CATEGORIES,
        reg_statuses=list(REG_STATUS_LABELS.items()),
        audit=audit, audit_actions=[(code, label) for code, label in AUDIT_ACTIONS.items()],
        audit_labels=AUDIT_ACTIONS,
        tab=tab, f=filters,
    )


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@roles_required(ROLE_ADMIN)
def change_role(user_id):
    try:
        role = request.form.get("role", "")
        auth_service.set_user_role(current_user, user_id, role)
        audit_service.log(current_user, "user.role_changed", "user", user_id, f"role={role}")
        flash("Пайдаланушы рөлі өзгертілді.", "success")
    except ServiceError as exc:
        if exc.status_code == 404:
            abort(404)
        flash(exc.message, "danger")
    return redirect(url_for("admin.dashboard") + "#users")


@bp.route("/users/<int:user_id>/approval", methods=["POST"])
@roles_required(ROLE_ADMIN)
def set_approval(user_id):
    try:
        value = request.form.get("approval", "")
        user = auth_service.set_approval(current_user, user_id, value)
        audit_service.log(current_user, "user.approved" if user["approval"] == APPROVAL_APPROVED
                          else "user.rejected", "user", user_id, f"approval={value}")
        flash("Ұйымдастырушы мақұлдалды." if user["approval"] == APPROVAL_APPROVED
              else "Ұйымдастырушының мақұлдауы жаңартылды.", "success")
        if user["approval"] == APPROVAL_APPROVED:
            mail_service.notify_approval(user)
    except ServiceError as exc:
        if exc.status_code == 404:
            abort(404)
        flash(exc.message, "danger")
    return redirect(url_for("admin.dashboard", tab="users") + "#users")


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@roles_required(ROLE_ADMIN)
def delete_user(user_id):
    try:
        paths = auth_service.delete_user(current_user, user_id)
        certificate_service.remove_files(paths)
        audit_service.log(current_user, "user.deleted", "user", user_id, f"user_id={user_id}")
        flash("Пайдаланушы жойылды.", "success")
    except ServiceError as exc:
        if exc.status_code == 404:
            abort(404)
        flash(exc.message, "danger")
    return redirect(url_for("admin.dashboard") + "#users")
