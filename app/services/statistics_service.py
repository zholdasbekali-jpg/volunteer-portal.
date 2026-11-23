"""Статистика (SQL-есептеулер) және Matplotlib графиктері.

Барлық сандар тек деректер қорынан алынады. organizer_id берілсе — тек сол
ұйымдастырушының іс-шаралары, әйтпесе (әкімші) — бүкіл платформа.
"""
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # серверде терезесіз жұмыс істеу үшін
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from ..database import get_db  # noqa: E402
from ..errors import NotFound  # noqa: E402
from ..i18n import translate as _  # noqa: E402
from ..models import CATEGORY_LABELS  # noqa: E402

GREEN = "#1b4d12"        # QAMQOR палитрасы
GREEN_LIGHT = "#6aa84f"
AMBER = "#d0b470"        # алтын
GRAY = "#b9b49f"
GREEN_DARK_HEX = "#103309"
DATE_FMT = "%Y-%m-%d %H:%M"
CHART_NAMES = ("summary", "events", "fill", "category")


def _scope(organizer_id):
    """Ұйымдастырушыға сүзгі: (SQL-бөлік, параметрлер)."""
    if organizer_id is None:
        return "", ()
    return " AND e.organizer_id = ?", (organizer_id,)


def get_summary(organizer_id=None) -> dict:
    """Жалпы көрсеткіштер. Толу көрсеткіші = тіркелгендер / (жарияланған іс-шаралар сыйымдылығы), %."""
    db = get_db()
    cond, params = _scope(organizer_id)
    events_total = db.execute(f"SELECT COUNT(*) FROM events e WHERE 1=1{cond}", params).fetchone()[0]
    regs_total, attended = db.execute(
        f"""SELECT COUNT(r.id), COALESCE(SUM(r.status = 'attended'), 0)
            FROM registrations r JOIN events e ON e.id = r.event_id WHERE 1=1{cond}""", params).fetchone()
    volunteers = db.execute(
        f"""SELECT COUNT(DISTINCT r.user_id) FROM registrations r
            JOIN events e ON e.id = r.event_id WHERE 1=1{cond}""", params).fetchone()[0]
    if organizer_id is None:  # платформада — барлық тіркелген эріктілер
        volunteers = db.execute("SELECT COUNT(*) FROM users WHERE role = 'volunteer'").fetchone()[0]
    capacity = db.execute(
        f"SELECT COALESCE(SUM(e.capacity), 0) FROM events e WHERE e.status = 'published'{cond}",
        params).fetchone()[0]
    published_regs = db.execute(
        f"""SELECT COUNT(r.id) FROM registrations r JOIN events e ON e.id = r.event_id
            WHERE e.status = 'published'{cond}""", params).fetchone()[0]
    fill_rate = round(published_regs * 100.0 / capacity, 1) if capacity else 0.0
    return {"events_total": events_total, "volunteers_total": volunteers,
            "registrations_total": regs_total, "attended_total": attended,
            "fill_rate": fill_rate}


def get_extended(organizer_id=None) -> dict:
    """V3: кеңейтілген көрсеткіштер. Ескі get_summary өзгермейді, жаңа кілттер бөлек.

    Қатысу %, күту тізімі, пікірлер/орташа баға, алдағы/өткен іс-шаралар саны
    және санаттар бойынша бөлініс. Барлығы organizer_id арқылы шектеледі.
    """
    db = get_db()
    cond, params = _scope(organizer_id)
    now_str = datetime.now().strftime(DATE_FMT)

    reg_row = db.execute(
        f"""SELECT COUNT(r.id) AS total, COALESCE(SUM(r.status = 'attended'), 0) AS attended
            FROM registrations r JOIN events e ON e.id = r.event_id WHERE 1=1{cond}""", params).fetchone()
    total_regs, attended = reg_row["total"], reg_row["attended"]
    attendance_rate = round(attended * 100.0 / total_regs, 1) if total_regs else 0.0

    waitlist_total = db.execute(
        f"SELECT COUNT(w.id) FROM waitlist w JOIN events e ON e.id = w.event_id WHERE 1=1{cond}",
        params).fetchone()[0]

    rev_row = db.execute(
        f"""SELECT COUNT(v.id) AS n, AVG(v.rating) AS avg
            FROM reviews v JOIN events e ON e.id = v.event_id WHERE 1=1{cond}""", params).fetchone()
    reviews_total = rev_row["n"]
    avg_rating = round(rev_row["avg"], 1) if reviews_total else None

    upcoming_total = db.execute(
        f"SELECT COUNT(*) FROM events e WHERE e.status = 'published' AND e.event_date >= ?{cond}",
        (now_str, *params)).fetchone()[0]
    past_total = db.execute(
        f"SELECT COUNT(*) FROM events e WHERE e.event_date < ?{cond}",
        (now_str, *params)).fetchone()[0]

    cat_rows = db.execute(
        f"""SELECT e.category AS code, COUNT(DISTINCT e.id) AS events, COUNT(r.id) AS registrations
            FROM events e LEFT JOIN registrations r ON r.event_id = e.id
            WHERE 1=1{cond} GROUP BY e.category ORDER BY registrations DESC, events DESC""",
        params).fetchall()
    by_category = [{"code": r["code"], "label": CATEGORY_LABELS.get(r["code"], r["code"]),
                    "events": r["events"], "registrations": r["registrations"]} for r in cat_rows]

    return {"attendance_rate": attendance_rate, "waitlist_total": waitlist_total,
            "reviews_total": reviews_total, "avg_rating": avg_rating,
            "upcoming_total": upcoming_total, "past_total": past_total,
            "by_category": by_category}


def get_event_stats(organizer_id=None):
    """Әр іс-шара бойынша: сыйымдылық, тіркелгендер, қатысқандар, толу %."""
    cond, params = _scope(organizer_id)
    rows = get_db().execute(
        f"""SELECT e.id, e.title, e.event_date, e.capacity,
                   COUNT(r.id) AS registered,
                   COALESCE(SUM(r.status = 'attended'), 0) AS attended
            FROM events e LEFT JOIN registrations r ON r.event_id = e.id
            WHERE 1=1{cond} GROUP BY e.id ORDER BY e.event_date""", params).fetchall()
    return [{**dict(r), "fill_rate": round(r["registered"] * 100.0 / r["capacity"], 1)} for r in rows]


def _short(title: str, n: int = 22) -> str:
    return title if len(title) <= n else title[: n - 1] + "…"


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _empty_chart(message="Деректер әзірге жоқ") -> bytes:
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.text(0.5, 0.5, _(message), ha="center", va="center", color=GRAY, fontsize=14)
    ax.axis("off")
    return _to_png(fig)


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)


def render_chart(name: str, organizer_id=None) -> bytes:
    """PNG-байттар қайтарады. Графиктегі жазулар ағылшынша (ТЗ рұқсат етеді).
    Барлық графиктер бірдей қаріп өлшемін қолданады; жартылай енді (6.5 дюйм) және
    толық енді (12 дюйм) өлшемдер беттегі баған енімен сәйкес келеді."""
    if name not in CHART_NAMES:
        raise NotFound("График табылмады.")
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 12})

    if name == "category":
        rows = get_extended(organizer_id)["by_category"]
        if not rows:
            return _empty_chart()
        fig, ax = plt.subplots(figsize=(6.5, max(3.6, 0.7 * len(rows) + 1.6)))
        ys = list(range(len(rows)))
        h = 0.32
        ax.barh([y - h for y in ys], [r["events"] for r in rows], h,
                label=_("Іс-шара саны"), color=GREEN)
        ax.barh([y + h for y in ys], [r["registrations"] for r in rows], h,
                label=_("Тіркелді"), color=AMBER)
        ax.set_yticks(ys, [_(r["label"]) for r in rows])
        ax.invert_yaxis()
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_title(_("Санаттар бойынша көрсеткіштер"), loc="left", fontweight="bold")
        ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
        ax.grid(axis="x", color="#e5e7eb")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        return _to_png(fig)

    if name == "summary":
        s = get_summary(organizer_id)
        labels = [_("Іс-шаралар"), _("Еріктілер"), _("Тіркелімдер"), _("Қатысты")]
        values = [s["events_total"], s["volunteers_total"], s["registrations_total"], s["attended_total"]]
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        bars = ax.bar(labels, values, color=[GREEN, GREEN_LIGHT, AMBER, GREEN_DARK_HEX])
        for b, v in zip(bars, values):
            ax.annotate(str(v), (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom",
                        xytext=(0, 3), textcoords="offset points", fontsize=11, fontweight="bold")
        ax.set_title(_("Жалпы көрсеткіштер"), loc="left", fontweight="bold")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        _style(ax)
        return _to_png(fig)

    stats = get_event_stats(organizer_id)
    if not stats:
        return _empty_chart()
    names = [_short(s["title"], 28) for s in stats]
    if name == "events":
        fig, ax = plt.subplots(figsize=(12, max(3.6, 0.8 * len(stats) + 1.6)))
        ys = list(range(len(stats)))
        h = 0.26
        ax.barh([y - h for y in ys], [s["capacity"] for s in stats], h, label=_("Орын саны"), color=GRAY)
        ax.barh(ys, [s["registered"] for s in stats], h, label=_("Тіркелді"), color=GREEN)
        ax.barh([y + h for y in ys], [s["attended"] for s in stats], h, label=_("Қатысты"), color=AMBER)
        ax.set_yticks(ys, names)
        ax.invert_yaxis()
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_title(_("Іс-шара бойынша қатысушылар"), loc="left", fontweight="bold")
        # Легенда графиктің сыртында: бағандарды жаппауы үшін
        ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
        ax.grid(axis="x", color="#e5e7eb")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        return _to_png(fig)

    # fill: толу көрсеткіші, %
    fig, ax = plt.subplots(figsize=(6.5, max(4.2, 0.5 * len(stats) + 1.6)))
    rates = [min(s["fill_rate"], 100) for s in stats]
    bars = ax.barh([_short(s["title"], 20) for s in stats], rates, color=[GREEN if r < 100 else AMBER for r in rates])
    for b, s in zip(bars, stats):
        ax.annotate(f"{s['fill_rate']:.0f}%", (b.get_width(), b.get_y() + b.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points", va="center", fontsize=10)
    ax.set_xlim(0, 115)
    ax.invert_yaxis()
    ax.set_xlabel(_("Толу көрсеткіші, %"))
    ax.set_title(_("Іс-шараның толуы"), loc="left", fontweight="bold")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return _to_png(fig)
