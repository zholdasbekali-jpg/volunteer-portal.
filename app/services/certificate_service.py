"""PDF-сертификаттар: беру шарттарын тексеру, бірегей нөмір, ReportLab арқылы PDF жасау."""
import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied
from ..models import REG_ATTENDED

FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
GREEN = colors.HexColor("#1f7a4d")
GREEN_DARK = colors.HexColor("#14532d")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
_fonts_ready = False

KZ_MONTHS = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
             "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"]


def _register_fonts() -> None:
    """Қазақ әріптері бар TTF қаріпті бір рет тіркейміз (стандартты Helvetica ә,ғ,қ-ны көрсетпейді)."""
    global _fonts_ready
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        _fonts_ready = True


def format_date_kz(value: str) -> str:
    """'2026-05-01 10:00' -> '2026 жылғы 1 мамыр'."""
    d = datetime.strptime(value[:10], "%Y-%m-%d")
    return f"{d.year} жылғы {d.day} {KZ_MONTHS[d.month - 1]}"


def generate_code(db) -> str:
    """Бірегей нөмір: VP-<жыл>-<8 hex>. Соқтығыс болса қайта жасалады."""
    for _ in range(10):
        code = f"VP-{datetime.now().year}-{secrets.token_hex(4).upper()}"
        if db.execute("SELECT 1 FROM certificates WHERE certificate_code = ?", (code,)).fetchone() is None:
            return code
    raise RuntimeError("Бірегей сертификат нөмірін жасау мүмкін болмады.")  # іс жүзінде болмайды


def _fit_text(c, text, font, size, max_width):
    """Мәтін ені шектен асса, қаріп өлшемін кішірейтеді."""
    while size > 10 and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def render_pdf(path: str, *, code, volunteer, event_title, event_date, issued_at, organizer) -> None:
    """Ресми үлгідегі A4 альбомдық сертификатты жасайды."""
    _register_fonts()
    w, h = landscape(A4)
    c = canvas.Canvas(path, pagesize=(w, h))
    c.setTitle(f"Сертификат {code}")
    c.setAuthor("Еріктілер іс-шаралары порталы")

    # Қосарлы жиек және бұрыштық әшекей
    c.setStrokeColor(GREEN_DARK)
    c.setLineWidth(4)
    c.rect(28, 28, w - 56, h - 56)
    c.setStrokeColor(GREEN)
    c.setLineWidth(1)
    c.rect(40, 40, w - 80, h - 80)
    c.setFillColor(GREEN)
    c.rect(28, h - 28 - 14, w - 56, 14, stroke=0, fill=1)  # жоғарғы жасыл жолақ

    c.setFillColor(GREEN_DARK)
    c.setFont(FONT_BOLD, 13)
    c.drawCentredString(w / 2, h - 85, "ЕРІКТІЛЕР ІС-ШАРАЛАРЫ ПОРТАЛЫ")
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 40)
    c.drawCentredString(w / 2, h - 145, "СЕРТИФИКАТ")
    c.setStrokeColor(GREEN)
    c.setLineWidth(2)
    c.line(w / 2 - 70, h - 160, w / 2 + 70, h - 160)

    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 13)
    c.drawCentredString(w / 2, h - 195, "Осы сертификат")

    size = _fit_text(c, volunteer, FONT_BOLD, 30, w - 160)
    c.setFillColor(GREEN_DARK)
    c.setFont(FONT_BOLD, size)
    c.drawCentredString(w / 2, h - 235, volunteer)
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.5)
    c.line(110, h - 245, w - 110, h - 245)

    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 13)
    c.drawCentredString(w / 2, h - 275, "ерікті ретінде келесі іс-шараға белсенді қатысқаны үшін табысталды:")
    size = _fit_text(c, f"«{event_title}»", FONT_BOLD, 22, w - 160)
    c.setFont(FONT_BOLD, size)
    c.drawCentredString(w / 2, h - 315, f"«{event_title}»")
    c.setFont(FONT_REGULAR, 13)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, h - 345, f"Өткізілген күні: {format_date_kz(event_date)}")

    # Төменгі блок: нөмір, берілген күні, ұйымдастырушы
    y = 110
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 10)
    c.drawString(80, y + 18, f"Сертификат нөмірі: {code}")
    c.drawString(80, y, f"Берілген күні: {format_date_kz(issued_at)}")
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    c.line(w - 300, y + 14, w - 80, y + 14)
    c.setFont(FONT_REGULAR, 10)
    c.drawCentredString(w - 190, y, f"Ұйымдастырушы: {organizer}")
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 8)
    c.drawCentredString(w / 2, 52, f"Түпнұсқалығын тексеру: /verify/{code}")
    c.showPage()
    c.save()


def issue_certificate(actor, registration_id: int):
    """Сертификатты береді (бар болса — қайтарады). Тек қатысуы расталған ерікті
    өз тіркелімі үшін ала алады. Нәтиже: certificates жолы."""
    db = get_db()
    row = db.execute(
        """SELECT r.id, r.user_id, r.status, u.full_name, e.title, e.event_date,
                  o.full_name AS organizer_name
           FROM registrations r JOIN users u ON u.id = r.user_id
           JOIN events e ON e.id = r.event_id JOIN users o ON o.id = e.organizer_id
           WHERE r.id = ?""", (registration_id,)).fetchone()
    if row is None:
        raise NotFound("Тіркелім табылмады.")
    if actor is None or row["user_id"] != actor["id"]:
        raise PermissionDenied("Басқа пайдаланушының сертификатын алуға болмайды.")
    if row["status"] != REG_ATTENDED:
        raise Conflict("Сертификат тек қатысуы расталған эріктіге беріледі.")

    existing = db.execute("SELECT * FROM certificates WHERE registration_id = ?", (registration_id,)).fetchone()
    if existing is not None and os.path.exists(existing["pdf_path"]):
        return existing

    out_dir = Path(current_app.config["CERTIFICATE_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    issued_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    with transaction() as tdb:
        if existing is None:
            code = generate_code(tdb)
        else:  # файл жоғалған: сол нөмірмен қайта жасаймыз
            code = existing["certificate_code"]
        pdf_path = str(out_dir / f"certificate_{code}.pdf")
        render_pdf(pdf_path, code=code, volunteer=row["full_name"], event_title=row["title"],
                   event_date=row["event_date"], issued_at=issued_at, organizer=row["organizer_name"])
        if existing is None:
            tdb.execute(
                "INSERT INTO certificates (registration_id, certificate_code, issued_at, pdf_path) VALUES (?, ?, ?, ?)",
                (registration_id, code, issued_at, pdf_path))
        else:
            tdb.execute("UPDATE certificates SET pdf_path = ? WHERE id = ?", (pdf_path, existing["id"]))
    return db.execute("SELECT * FROM certificates WHERE registration_id = ?", (registration_id,)).fetchone()


def list_available(user_id: int):
    """Эріктінің сертификат алуға құқығы бар (қатысуы расталған) тіркелімдері."""
    return get_db().execute(
        """SELECT r.id AS registration_id, e.title, e.event_date, c.certificate_code, c.issued_at
           FROM registrations r JOIN events e ON e.id = r.event_id
           LEFT JOIN certificates c ON c.registration_id = r.id
           WHERE r.user_id = ? AND r.status = 'attended' ORDER BY e.event_date DESC""",
        (user_id,)).fetchall()


def verify(code: str):
    """Сертификат нөмірі бойынша түпнұсқалығын тексеру (жария бет)."""
    return get_db().execute(
        """SELECT c.certificate_code, c.issued_at, u.full_name, e.title, e.event_date
           FROM certificates c JOIN registrations r ON r.id = c.registration_id
           JOIN users u ON u.id = r.user_id JOIN events e ON e.id = r.event_id
           WHERE c.certificate_code = ?""", ((code or "").strip().upper(),)).fetchone()


def remove_files(paths) -> None:
    """Жойылған жазбалардың PDF файлдарын өшіреді (қате болса үнсіз өткізеді)."""
    for p in paths or []:
        try:
            os.remove(p)
        except OSError:
            pass
