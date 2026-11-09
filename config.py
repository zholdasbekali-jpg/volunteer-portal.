"""Қосымша конфигурациясы.

Құпия мәндер Git-ке түспейді: SECRET_KEY ортаның айнымалысынан алынады,
ал болмаса instance/secret_key файлында бір рет жасалып сақталады
(instance/ бумасы .gitignore ішінде).
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
GENERATED_DIR = BASE_DIR / "generated"


def _load_secret_key() -> str:
    """SECRET_KEY: env -> instance/secret_key -> жаңа кездейсоқ кілт."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    INSTANCE_DIR.mkdir(exist_ok=True)
    key_file = INSTANCE_DIR / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Негізгі (өндірістік) параметрлер. DEBUG әдепкіде өшірулі."""

    DEBUG = _env_bool("FLASK_DEBUG", False)
    SECRET_KEY = _load_secret_key()
    DATABASE = os.environ.get("DATABASE", str(INSTANCE_DIR / "volunteer.db"))
    CERTIFICATE_DIR = os.environ.get("CERTIFICATE_DIR", str(GENERATED_DIR / "certificates"))
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    MAX_CONTENT_LENGTH = 1024 * 1024  # 1 МБ: форма деректері үшін жеткілікті


class TestConfig(Config):
    """Тестке арналған параметрлер (жеке уақытша деректер қоры)."""

    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key-not-for-production"
    CSRF_ENABLED = False
