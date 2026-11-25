"""PDF-сертификаттар: беру шарттарын тексеру, бірегей нөмір, ReportLab арқылы PDF жасау."""
import logging
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from flask import current_app
from PIL import Image
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..database import get_db, transaction
from ..errors import Conflict, NotFound, PermissionDenied
from ..models import REG_ATTENDED

FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
IMAGE_DIR = FONT_DIR.parent / "images"
LOGO_NAMES = ("logo.png", "logo.jpg", "logo.jpeg")  # бірінші табылған файл қолданылады
SERIF = "DejaVuSerif"
SERIF_BOLD = "DejaVuSerif-Bold"
SERIF_ITALIC = "DejaVuSerif-Italic"

# ---- Дизайн параметрлері (QAMQOR стилі): осы жерден түстер мен мәтінді өзгертуге болады ----
BG = colors.HexColor("#103309")      # қою жасыл фон
GOLD = colors.HexColor("#d0b470")    # алтын: жиектер, тақырып
IVORY = colors.HexColor("#f4efe0")   # негізгі мәтін
PROJECT_HANDLE = "@Qamqor_11"
CERT_LANG = "kk"                     # "kk" — қазақша, "ru" — орысша мәтін
TEXTS = {
    "kk": {
        "title": "СЕРТИФИКАТ",
        "awarded": "Осы сертификат табысталады",
        "reason": ["белсенді қатысқаны, адалдығы және жан жомарттығы үшін,",
                   "«QAMQOR» волонтерлік жобасының іс-шарасында көрсеткен:"],
        "event_date": "Өткізілген күні",
        "issued": "Берілген күні",
        "organizer": "Ұйымдастырушы",
        "number": "Сертификат нөмірі",
        "verify": "Түпнұсқалығын тексеру",
        "scan": "QR арқылы тексеріңіз",
        "portal": "ЕРІКТІЛЕР ІС-ШАРАЛАРЫ ПОРТАЛЫ",
    },
    "ru": {
        "title": "СЕРТИФИКАТ",
        "awarded": "Настоящий сертификат вручается",
        "reason": ["за активное участие, добросовестность и щедрость души,",
                   "проявленные в мероприятиях волонтёрского проекта «QAMQOR»:"],
        "event_date": "Дата проведения",
        "issued": "Дата выдачи",
        "organizer": "Организатор",
        "number": "Номер сертификата",
        "verify": "Проверка подлинности",
        "scan": "Проверка по QR-коду",
        "portal": "ПОРТАЛ ВОЛОНТЁРСКИХ МЕРОПРИЯТИЙ",
    },
    "en": {
        "title": "CERTIFICATE",
        "awarded": "This certificate is awarded to",
        "reason": ["for active participation, integrity and generosity of spirit",
                   "shown at an event of the “QAMQOR” volunteer project:"],
        "event_date": "Event date",
        "issued": "Issued",
        "organizer": "Organizer",
        "number": "Certificate number",
        "verify": "Verify authenticity",
        "scan": "Scan the QR code to verify",
        "portal": "VOLUNTEER EVENTS PORTAL",
    },
}
_fonts_ready = False
log = logging.getLogger(__name__)

KZ_MONTHS = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
             "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"]


def _register_fonts() -> None:
    """Қазақ әріптері бар TTF қаріптерді бір рет тіркейміз (стандартты Helvetica ә,ғ,қ-ны көрсетпейді)."""
    global _fonts_ready
    if not _fonts_ready:
        for name, file in ((SERIF, "DejaVuSerif.ttf"), (SERIF_BOLD, "DejaVuSerif-Bold.ttf"),
                           (SERIF_ITALIC, "DejaVuSerif-Italic.ttf")):
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
        _fonts_ready = True


RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


EN_MONTHS = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]


def _fmt_date(value: str, lang: str = "") -> str:
    """Күнді сертификат тіліне сай пішімдейді (lang бос болса — CERT_LANG)."""
    lang = lang or CERT_LANG
    d = datetime.strptime(value[:10], "%Y-%m-%d")
    if lang == "ru":
        return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year} г."
    if lang == "en":
        return f"{d.day} {EN_MONTHS[d.month - 1]} {d.year}"
    return format_date_kz(value)


def format_date_kz(value: str) -> str:
    """'2026-05-01 10:00' -> '2026 жылғы 1 мамыр'."""
    d = datetime.strptime(value[:10], "%Y-%m-%d")
    return f"{d.year} жылғы {d.day} {KZ_MONTHS[d.month - 1]}"


CODE_RE = re.compile(r"VP-\d{4}-[0-9A-F]{8}", re.IGNORECASE)


def extract_code(text: str):
    """QR мәтінінен (толық сілтеме) немесе қолмен енгізілген жолдан сертификат нөмірін алады.
    Қай сайттың сілтемесі екені маңызды емес: нөмірдің өзі ғана алынады. Табылмаса None."""
    match = CODE_RE.search(text or "")
    return match.group(0).upper() if match else None


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


def find_logo():
    """app/static/images/ ішіндегі logo.png/jpg жолын қайтарады, жоқ болса None."""
    for name in LOGO_NAMES:
        path = IMAGE_DIR / name
        if path.exists():
            return str(path)
    return None


def _load_logo():
    """Логотипті сертификат фонына (BG) кіріктіріп, мөлдірлік (alpha) өңдеуінсіз RGB түрінде береді:
    сондықтан кез келген ортада (Windows, Termux) бірдей көрінеді. Қате болса — журналға жазылады
    (үнсіз өтпейді), сертификат логотипсіз жасалады."""
    path = find_logo()
    if not path:
        return None
    try:
        img = Image.open(path).convert("RGBA")
        base = Image.new("RGBA", img.size, (16, 51, 9, 255))
        base.alpha_composite(img)
        return ImageReader(base.convert("RGB"))
    except Exception as exc:  # бүлінген сурет сертификат берілуін тоқтатпауы керек
        log.warning("Сертификат логотипін оқу мүмкін болмады (%s): %s", path, exc)
        return None


def _spaced(c, text, font, size, y, w, space, color):
    """Әріп аралығы үлкейтілген мәтінді беттің ортасына салады."""
    width = pdfmetrics.stringWidth(text, font, size) + space * (len(text) - 1)
    c.saveState()  # әріп аралығы келесі мәтіндерге «ағып» кетпеуі үшін күйді оқшаулаймыз
    t = c.beginText(w / 2 - width / 2, y)
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(space)
    t.textLine(text)
    c.drawText(t)
    c.restoreState()


def _heart(c, cx, cy, r):
    """Тақырып астындағы кішкентай жүрек (контур)."""
    p = c.beginPath()
    p.moveTo(cx, cy - r)
    p.curveTo(cx - 1.6 * r, cy - 0.1 * r, cx - 1.0 * r, cy + 1.1 * r, cx, cy + 0.35 * r)
    p.curveTo(cx + 1.0 * r, cy + 1.1 * r, cx + 1.6 * r, cy - 0.1 * r, cx, cy - r)
    c.drawPath(p, stroke=1, fill=0)


def _draw_frame(c, w, h):
    """Фон, бұрыштық доғалар, қосарлы дөңгелектелген алтын жиек."""
    c.setFillColor(BG)
    c.rect(0, 0, w, h, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    for cx, cy, start in ((0, h, 270), (w, h, 180), (0, 0, 0), (w, 0, 90)):
        for r in (96, 110):
            c.arc(cx - r, cy - r, cx + r, cy + r, startAng=start, extent=90)
    c.setLineWidth(1.8)
    c.roundRect(28, 28, w - 56, h - 56, 16, stroke=1, fill=0)
    c.setLineWidth(0.6)
    c.roundRect(40, 40, w - 80, h - 80, 11, stroke=1, fill=0)


def _draw_header(c, w, h, t) -> None:
    """Жоғарғы орталықта логотип; файл жоқ немесе бүлінген болса — порталдың атауы."""
    logo = _load_logo()
    if logo is not None:
        lw = 230
        c.drawImage(logo, w / 2 - lw / 2, h - 46 - 120, width=lw, height=120,
                    preserveAspectRatio=True, anchor="c")
        return
    _spaced(c, t["portal"], SERIF_BOLD, 14, h - 100, w, 2, GOLD)


def _draw_qr(c, x, y, size, url) -> None:
    """Ашық түсті тақтайшадағы қою жасыл QR: қою фонда да сканерлеуге ыңғайлы (контраст).
    QR-дың өз «тыныш аймағы» (quiet zone) тақтайша ішінде қалады."""
    widget = qr.QrCodeWidget(url, barLevel="M")
    widget.barFillColor = BG
    widget.barStrokeColor = BG
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    c.setFillColor(IVORY)
    c.roundRect(x, y, size, size, 5, stroke=0, fill=1)
    renderPDF.draw(drawing, c, x, y)


def render_pdf(path: str, *, code, volunteer, event_title, event_date, issued_at, organizer, city="",
               verify_url="", lang="") -> None:
    """QAMQOR стиліндегі A4 альбомдық сертификатты жасайды (мәтін TEXTS[lang], lang бос болса — CERT_LANG)."""
    _register_fonts()
    lang = lang if lang in TEXTS else CERT_LANG
    t = TEXTS[lang]
    w, h = landscape(A4)
    c = canvas.Canvas(path, pagesize=(w, h))
    c.setTitle(f"{t['title']} {code}")
    c.setAuthor("QAMQOR")
    _draw_frame(c, w, h)
    _draw_header(c, w, h, t)

    # Тақырып пен жүрегі бар бөлгіш
    _spaced(c, t["title"], SERIF_BOLD, 40, h - 250, w, 7, GOLD)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(w / 2 - 190, h - 276, w / 2 - 20, h - 276)
    c.line(w / 2 + 20, h - 276, w / 2 + 190, h - 276)
    _heart(c, w / 2, h - 276, 6)

    c.setFillColor(IVORY)
    c.setFont(SERIF, 15)
    c.drawCentredString(w / 2, h - 308, t["awarded"])

    size = _fit_text(c, volunteer, SERIF_ITALIC, 30, w - 220)
    c.setFont(SERIF_ITALIC, size)
    c.drawCentredString(w / 2, h - 346, volunteer)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.7)
    c.line(w / 2 - 250, h - 358, w / 2 + 250, h - 358)

    c.setFillColor(IVORY)
    c.setFont(SERIF, 12.5)
    c.drawCentredString(w / 2, h - 386, t["reason"][0])
    c.drawCentredString(w / 2, h - 404, t["reason"][1])
    quoted = f"«{event_title}»"
    size = _fit_text(c, quoted, SERIF_BOLD, 20, w - 160)
    c.setFillColor(GOLD)
    c.setFont(SERIF_BOLD, size)
    c.drawCentredString(w / 2, h - 434, quoted)
    c.setFillColor(IVORY)
    c.setFont(SERIF, 11.5)
    when = f"{t['event_date']}: {_fmt_date(event_date, lang)}" + (f", {city}" if city else "")
    c.drawCentredString(w / 2, h - 456, when)

    c.setFillColor(GOLD)
    c.setFont(SERIF, 12)
    c.drawCentredString(w / 2, 124 if verify_url else 100, PROJECT_HANDLE)

    # Төменгі қатар: берілген күні | нөмір және тексеру | ұйымдастырушы
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    c.line(80, 76, 290, 76)
    c.line(w - 290, 76, w - 80, 76)
    c.setFillColor(IVORY)
    c.setFont(SERIF, 10)
    c.drawString(80, 62, f"{t['issued']}: {_fmt_date(issued_at, lang)}")
    org = f"{t['organizer']}: {organizer}"
    c.drawRightString(w - 80, 62, org if pdfmetrics.stringWidth(org, SERIF, 10) <= 210 else organizer)
    c.setFillColor(GOLD)
    c.setFont(SERIF, 8)
    if verify_url:
        # Төменгі ортада QR, сол жағында нөмір, оң жағында нұсқау
        _draw_qr(c, w / 2 - 31, 44, 62, verify_url)
        c.drawRightString(w / 2 - 40, 72, f"{t['number']}:")
        c.drawRightString(w / 2 - 40, 61, code)
        c.drawString(w / 2 + 40, 66, t["scan"])
    else:
        c.drawCentredString(w / 2, 66, f"{t['number']}: {code}")
        c.drawCentredString(w / 2, 54, f"{t['verify']}: /verify/{code}")
    c.showPage()
    c.save()


def issue_certificate(actor, registration_id: int, base_url: str = "", lang: str = ""):
    """Сертификатты береді (бар болса — қайтарады). Тек қатысуы расталған ерікті
    өз тіркелімі үшін ала алады. base_url берілсе, PDF-ке /verify/<нөмір> сілтемесі бар QR қосылады.
    Нәтиже: certificates жолы."""
    db = get_db()
    row = db.execute(
        """SELECT r.id, r.user_id, r.status, u.full_name, e.title, e.event_date, e.city,
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
        # Құлыпты алғаннан кейін қайта тексереміз: екі қатар сұрау (қос басу) бір сертификатты
        # екі рет жасап, UNIQUE қатесімен құламауы үшін
        again = tdb.execute("SELECT * FROM certificates WHERE registration_id = ?", (registration_id,)).fetchone()
        if again is not None and os.path.exists(again["pdf_path"]):
            return again
        existing = again
        if existing is None:
            code = generate_code(tdb)
        else:  # файл жоғалған: сол нөмірмен қайта жасаймыз
            code = existing["certificate_code"]
        pdf_path = str(out_dir / f"certificate_{code}.pdf")
        render_pdf(pdf_path, code=code, volunteer=row["full_name"], event_title=row["title"],
                   event_date=row["event_date"], issued_at=issued_at, organizer=row["organizer_name"],
                   city=row["city"], lang=lang,
                   verify_url=f"{base_url.rstrip('/')}/verify/{code}" if base_url else "")
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
