"""Қосымша фабрикасы: Flask, Flask-Login, CSRF, фильтрлер, қате беттері, CLI-командалар."""
from pathlib import Path

import click
from flask import Flask, render_template, request
from flask_login import LoginManager

from config import Config

from . import database
from .models import (EVENT_STATUS_LABELS, REG_STATUS_LABELS, ROLE_LABELS, User)
from .security import csrf_protect, get_csrf_token
from .services import auth_service, certificate_service, event_service

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Бұл бетті көру үшін жүйеге кіріңіз."
login_manager.login_message_category = "warning"

KZ_MONTHS = certificate_service.KZ_MONTHS


def kz_datetime(value: str, with_time: bool = True) -> str:
    """'2026-05-01 10:00' -> '1 мамыр 2026, 10:00'."""
    if not value:
        return ""
    y, m, d = int(value[:4]), int(value[5:7]), int(value[8:10])
    text = f"{d} {KZ_MONTHS[m - 1]} {y}"
    return f"{text}, {value[11:16]}" if with_time and len(value) >= 16 else text


def create_app(config_object=None, **overrides) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object or Config)
    app.config.update(overrides)
    Path(app.config["CERTIFICATE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    login_manager.init_app(app)
    app.teardown_appcontext(database.close_db)
    app.before_request(csrf_protect)

    @login_manager.user_loader
    def load_user(user_id):
        row = auth_service.get_user(user_id)
        return User(row) if row else None

    app.jinja_env.globals["csrf_token"] = get_csrf_token
    app.jinja_env.globals["now_str"] = event_service.now_str
    app.jinja_env.filters["kz_datetime"] = kz_datetime
    app.jinja_env.filters["kz_date"] = lambda v: kz_datetime(v, with_time=False)
    app.jinja_env.globals.update(ROLE_LABELS=ROLE_LABELS, EVENT_STATUS_LABELS=EVENT_STATUS_LABELS,
                                 REG_STATUS_LABELS=REG_STATUS_LABELS)

    from . import admin, auth, certificates, events, registrations, statistics
    for module in (auth, events, registrations, certificates, statistics, admin):
        app.register_blueprint(module.bp)

    register_error_handlers(app)
    register_cli(app)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    with app.app_context():
        database.init_db()
    return app


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
