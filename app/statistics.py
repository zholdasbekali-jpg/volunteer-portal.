"""Статистика беті және Matplotlib графиктері (PNG)."""
from flask import Blueprint, Response, abort, render_template
from flask_login import current_user

from .auth import roles_required
from .errors import ServiceError
from .models import ROLE_ADMIN, ROLE_ORGANIZER
from .services import statistics_service

bp = Blueprint("statistics", __name__)


def _scope():
    """Ұйымдастырушы тек өз деректерін көреді, әкімші — барлығын."""
    return None if current_user.is_admin else current_user.id


@bp.route("/statistics")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def page():
    scope = _scope()
    return render_template("statistics.html", summary=statistics_service.get_summary(scope),
                           stats=statistics_service.get_event_stats(scope))


@bp.route("/statistics/chart/<name>.png")
@roles_required(ROLE_ORGANIZER, ROLE_ADMIN)
def chart(name):
    try:
        png = statistics_service.render_chart(name, _scope())
    except ServiceError:
        abort(404)
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})
