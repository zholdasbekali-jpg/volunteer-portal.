"""Кіру әрекеттерін шектеу (brute-force қорғанысы).

Сәтсіз әрекеттер деректер қорында санаумен сақталады, сондықтан бірнеше процесс (gunicorn workers) және
қайта іске қосу кезінде де жұмыс істейді. Екі кілт: email бойынша (нақты аккаунтты болжау) және IP бойынша.
"""
import math
import time

from ..database import transaction
from ..errors import TooManyAttempts

WINDOW_SECONDS = 15 * 60      # сәтсіздіктер осы мерзімде есептеледі
LOCK_SECONDS = 5 * 60         # бұғаттау ұзақтығы
LIMITS = {"e": 5, "i": 30}    # email бойынша 5, IP бойынша 30 сәтсіз әрекет


def _keys(email: str, ip: str):
    return [("e", f"e:{(email or '').strip().lower()[:254]}"), ("i", f"i:{ip or 'unknown'}")]


def check(email: str, ip: str, now: float | None = None) -> None:
    """Бұғатталған болса, TooManyAttempts көтереді (құпиясөз тексерілместен бұрын шақырылады)."""
    now = time.time() if now is None else now
    with transaction() as db:
        for _kind, key in _keys(email, ip):
            row = db.execute("SELECT locked_until FROM login_attempts WHERE key = ?", (key,)).fetchone()
            if row and row["locked_until"] > now:
                minutes = max(1, math.ceil((row["locked_until"] - now) / 60))
                raise TooManyAttempts(f"Тым көп сәтсіз әрекет. {minutes} минуттан кейін қайталаңыз.")


def record_failure(email: str, ip: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with transaction() as db:
        # Мерзімі өткен, бұғатталмаған жазбалар пайдасыз: кесте ойдан шығарылған email-дермен өспесін
        db.execute("DELETE FROM login_attempts WHERE window_start < ? AND locked_until < ?",
                   (now - WINDOW_SECONDS, now))
        for kind, key in _keys(email, ip):
            row = db.execute("SELECT fails, window_start FROM login_attempts WHERE key = ?", (key,)).fetchone()
            if row is None or now - row["window_start"] > WINDOW_SECONDS:
                fails, start = 1, now
            else:
                fails, start = row["fails"] + 1, row["window_start"]
            locked = now + LOCK_SECONDS if fails >= LIMITS[kind] else 0
            db.execute("""INSERT INTO login_attempts (key, fails, window_start, locked_until) VALUES (?,?,?,?)
                          ON CONFLICT(key) DO UPDATE SET fails=excluded.fails,
                          window_start=excluded.window_start, locked_until=excluded.locked_until""",
                       (key, fails, start, locked))
            if locked:
                # бұғаттан кейін есептегіш нөлден басталады
                db.execute("UPDATE login_attempts SET fails = 0 WHERE key = ?", (key,))


def reset(email: str) -> None:
    """Сәтті кіруде email есептегішін тазалайды (IP есептегіші өз мерзімімен ескіреді)."""
    with transaction() as db:
        db.execute("DELETE FROM login_attempts WHERE key = ?", (f"e:{(email or '').strip().lower()[:254]}",))
