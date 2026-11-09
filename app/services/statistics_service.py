"""Статистика (SQL-есептеулер) және Matplotlib графиктері.

Барлық сандар тек деректер қорынан алынады. organizer_id берілсе — тек сол
ұйымдастырушының іс-шаралары, әйтпесе (әкімші) — бүкіл платформа.
"""
import io

import matplotlib

matplotlib.use("Agg")  # серверде терезесіз жұмыс істеу үшін
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from ..database import get_db  # noqa: E402
from ..errors import NotFound  # noqa: E402

GREEN = "#1f7a4d"
GREEN_LIGHT = "#8fd0ad"
AMBER = "#e0a526"
GRAY = "#9aa5a0"
GREEN_DARK_HEX = "#14532d"
CHART_NAMES = ("summary", "events", "fill")


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


def _empty_chart(message="No data yet") -> bytes:
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.text(0.5, 0.5, message, ha="center", va="center", color=GRAY, fontsize=14)
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
    if name == "summary":
        s = get_summary(organizer_id)
        labels = ["Events", "Volunteers", "Registrations", "Attended"]
        values = [s["events_total"], s["volunteers_total"], s["registrations_total"], s["attended_total"]]
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        bars = ax.bar(labels, values, color=[GREEN, GREEN_LIGHT, AMBER, GREEN_DARK_HEX])
        for b, v in zip(bars, values):
            ax.annotate(str(v), (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom",
                        xytext=(0, 3), textcoords="offset points", fontsize=11, fontweight="bold")
        ax.set_title("Summary", loc="left", fontweight="bold")
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
        ax.barh([y - h for y in ys], [s["capacity"] for s in stats], h, label="Capacity", color=GRAY)
        ax.barh(ys, [s["registered"] for s in stats], h, label="Registered", color=GREEN)
        ax.barh([y + h for y in ys], [s["attended"] for s in stats], h, label="Attended", color=AMBER)
        ax.set_yticks(ys, names)
        ax.invert_yaxis()
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_title("Participants per event", loc="left", fontweight="bold")
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
    ax.set_xlabel("Fill rate, %")
    ax.set_title("Event fill rate", loc="left", fontweight="bold")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return _to_png(fig)
