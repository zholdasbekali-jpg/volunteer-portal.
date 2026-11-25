"""Қосымша фабрикасы: Flask, Flask-Login, CSRF, фильтрлер, қате беттері, CLI-командалар."""
from pathlib import Path

import click
from flask import Flask, render_template, request, url_for
from flask_login import LoginManager, current_user
from werkzeug.routing import IntegerConverter

from config import Config

from . import database, i18n
from .models import (CATEGORY_LABELS, EVENT_STATUS_LABELS, REG_STATUS_LABELS, ROLE_LABELS, User)
from .security import csrf_protect, get_csrf_token
from .services import auth_service, certificate_service, event_service, mail_service

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Бұл бетті көру үшін жүйеге кіріңіз."
login_manager.login_message_category = "warning"

KZ_MONTHS = certificate_service.KZ_MONTHS


def kz_datetime(value: str, with_time: bool = True) -> str:
    """'2026-05-01 10:00' -> '1 мамыр 2026, 10:00' (ағымдағы тілде: орысша «1 мая 2026», ағылшынша «1 May 2026»)."""
    return i18n.format_date(value, with_time)


class SafeIntConverter(IntegerConverter):
    """<int:id> SQLite INTEGER диапазонынан аспайды: өте үлкен сан 500 емес, 404 береді."""

    def __init__(self, map, fixed_digits=0, min=None, max=2 ** 63 - 1, signed=False):
        super().__init__(map, fixed_digits=fixed_digits, min=min, max=max, signed=signed)


def create_app(config_object=None, **overrides) -> Flask:
    app = Flask(__name__)
    app.url_map.converters["int"] = SafeIntConverter
    app.config.from_object(config_object or Config)
    app.config.update(overrides)
    Path(app.config["CERTIFICATE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    if app.config.get("TRUST_PROXY"):
        # Render/Heroku сияқты проксидің артында: нақты IP мен https схемасын X-Forwarded-* арқылы алу
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    login_manager.init_app(app)
    mail_service.init_app(app)
    app.teardown_appcontext(database.close_db)
    app.before_request(csrf_protect)

    @login_manager.user_loader
    def load_user(user_id):
        row = auth_service.get_user(user_id)
        return User(row) if row else None

    # Статикалық файл өзгерсе, браузер кэшіндегі ескі нұсқаны көрсетпеуі үшін ?v=<өзгерген уақыты>
    static_dir = Path(app.static_folder)
    asset_version = str(int(max((f.stat().st_mtime for f in static_dir.rglob("*")
                                 if f.is_file() and f.suffix in {".css", ".png", ".js"}), default=0)))

    @app.context_processor
    def inject_static_url():
        return {"static_url": lambda name: url_for("static", filename=name, v=asset_version)}

    app.jinja_env.globals["_"] = i18n.translate
    app.context_processor(i18n.context)
    app.jinja_env.globals["csrf_token"] = get_csrf_token
    app.jinja_env.globals["now_str"] = event_service.now_str
    app.jinja_env.filters["full_address"] = event_service.full_address
    app.jinja_env.filters["kz_datetime"] = kz_datetime
    app.jinja_env.filters["kz_date"] = lambda v: kz_datetime(v, with_time=False)
    app.jinja_env.globals.update(CATEGORY_LABELS=CATEGORY_LABELS, ROLE_LABELS=ROLE_LABELS,
                                 EVENT_STATUS_LABELS=EVENT_STATUS_LABELS,
                                 REG_STATUS_LABELS=REG_STATUS_LABELS)

    from . import (admin, auth, cabinet, certificates, checkin, events, registrations, statistics,
                   volunteers)
    for module in (auth, events, registrations, certificates, checkin, cabinet, volunteers, statistics, admin, i18n):
        app.register_blueprint(module.bp)

    register_error_handlers(app)
    register_cli(app)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Камера тек өз сайтымызға (QR-сканер) рұқсат; микрофон, геолокация өшірулі
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=()")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if app.config.get("SESSION_COOKIE_SECURE"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        # Жеке беттер шыққаннан кейін «Артқа» батырмасымен кэштен көрінбеуі үшін
        if current_user.is_authenticated and not request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    with app.app_context():
        database.init_db()
    return app


# Барлық скрипт пен стиль өз сайтымыздан; сыртқы мекенжайға форма жіберуге, frame-ге салуға тыйым
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

ERROR_TEXT = {
    400: ("Сұрау қате", "Сұрауды өңдеу мүмкін болмады."),
    403: ("Қолжетімділік жоқ", "Бұл бетке кіруге сіздің құқығыңыз жеткіліксіз."),
    404: ("Бет табылмады", "Сіз іздеген бет жоқ немесе жойылған."),
    413: ("Файл тым үлкен", "Жіберілген деректер көлемі шектен асты."),
    500: ("Сервер қатесі", "Күтпеген қате орын алды. Кейінірек қайталап көріңіз."),
}


def register_error_handlers(app: Flask) -> None:
    def handler(err):
        code = getattr(err, "code", 500) or 500
        title, text = ERROR_TEXT.get(code, ERROR_TEXT[500])
        detail = getattr(err, "description", "") if code == 400 else ""
        return render_template("errors/error.html", code=code, title=title,
                               text=detail or text), code

    for code in ERROR_TEXT:
        app.register_error_handler(code, handler)


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Деректер қорын (кестелерді) құру."""
        database.init_db()
        click.echo("Деректер қоры дайын.")

    @app.cli.command("notify-upcoming")
    @click.option("--days", type=int, default=None,
                  help="Хабарлама қанша күн бұрын жіберіледі (әдепкі — MAIL_REMINDER_DAYS).")
    def notify_upcoming_command(days):
        """Жақында өтетін іс-шараларға тіркелген еріктілерге хат жіберу."""
        click.echo(f"Жіберілген хаттар саны: {mail_service.send_upcoming_reminders(days)}")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Демо-деректерді (әкімші, ұйымдастырушылар, эріктілер, іс-шаралар) жүктеу."""
        from .seed import seed_demo
        click.echo(seed_demo())

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Аты-жөні")
    @click.password_option()
    def create_admin_command(email, name, password):
        """Әкімші пайдаланушыны құру."""
        auth_service.create_user_unchecked(name, email, password, "admin")
        click.echo("Әкімші құрылды.")
