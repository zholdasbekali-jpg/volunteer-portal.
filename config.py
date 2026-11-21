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
    # QR-кодтағы тексеру сілтемесінің негізі (мыс. https://portal.example.kz). Бос болса — сұрау келген мекенжай.
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip()
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # https-те жұмыс істегенде SESSION_COOKIE_SECURE=1 қойыңыз (кукилер тек шифрланған байланыспен жіберіледі)
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", PUBLIC_URL.startswith("https://"))
    # Render сияқты проксидің артында TRUST_PROXY=1: IP мен https дұрыс танылады
    TRUST_PROXY = _env_bool("TRUST_PROXY", False)
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 сағат
    MAX_CONTENT_LENGTH = 1024 * 1024  # 1 МБ: форма деректері үшін жеткілікті


class TestConfig(Config):
    """Тестке арналған параметрлер (жеке уақытша деректер қоры)."""

    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key-not-for-production"
    CSRF_ENABLED = False
