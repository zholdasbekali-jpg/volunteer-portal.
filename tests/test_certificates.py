"""FR-07: PDF-сертификат, бірегей нөмір, қол жеткізу шектеулері."""
import os

import pytest

from app.database import get_db
from app.errors import Conflict, NotFound, PermissionDenied
from app.services import certificate_service as cs
from app.services import registration_service as rs
from conftest import login


def attended(make, days=-3):
    org, vol = make.user("organizer"), make.user("volunteer", name="Асем Сәрсенбай")
    eid = make.event(org, days=days, title="Қала саябағын тазалау")
    rid = make.registration(vol, eid, "attended")
    return org, vol, eid, rid


def test_certificate_issued_for_attended(ctx, make):
    _, vol, _, rid = attended(make)
    cert = cs.issue_certificate(vol, rid)
    assert cert["certificate_code"].startswith("VP-")
    assert os.path.exists(cert["pdf_path"])
    with open(cert["pdf_path"], "rb") as f:
        data = f.read()
    assert data.startswith(b"%PDF") and len(data) > 2000


def test_certificate_is_idempotent_and_codes_unique(ctx, make):
    _, vol, _, rid = attended(make)
    first = cs.issue_certificate(vol, rid)
    again = cs.issue_certificate(vol, rid)
    assert first["certificate_code"] == again["certificate_code"]
    _, vol2, _, rid2 = attended(make)
    other = cs.issue_certificate(vol2, rid2)
    assert other["certificate_code"] != first["certificate_code"]
    assert get_db().execute("SELECT COUNT(*) FROM certificates").fetchone()[0] == 2


@pytest.mark.parametrize("status", ["absent", "pending"])
def test_certificate_denied_when_not_attended(ctx, make, status):
    org, vol = make.user("organizer"), make.user()
    rid = make.registration(vol, make.event(org, days=-2), status)
    with pytest.raises(Conflict):
        cs.issue_certificate(vol, rid)
    assert get_db().execute("SELECT COUNT(*) FROM certificates").fetchone()[0] == 0


def test_certificate_denied_for_other_user(ctx, make):
    _, _, _, rid = attended(make)
    stranger = make.user()
    with pytest.raises(PermissionDenied):
        cs.issue_certificate(stranger, rid)
    with pytest.raises(NotFound):
        cs.issue_certificate(stranger, 4040)


def test_certificate_removed_if_attendance_revoked(ctx, make):
    org, vol, _, rid = attended(make)
    cert = cs.issue_certificate(vol, rid)
    removed = rs.set_attendance(org, rid, "absent")
    cs.remove_files(removed)
    assert not os.path.exists(cert["pdf_path"])
    assert get_db().execute("SELECT COUNT(*) FROM certificates").fetchone()[0] == 0


def test_certificate_regenerated_if_file_missing(ctx, make):
    _, vol, _, rid = attended(make)
    cert = cs.issue_certificate(vol, rid)
    os.remove(cert["pdf_path"])
    again = cs.issue_certificate(vol, rid)
    assert again["certificate_code"] == cert["certificate_code"] and os.path.exists(again["pdf_path"])


def test_long_names_do_not_break_pdf(ctx, make, tmp_path):
    out = str(tmp_path / "long.pdf")
    cs.render_pdf(out, code="VP-2026-TEST", volunteer="Өте ұзын аты-жөні " * 6,
                  event_title="Өте ұзын іс-шара атауы " * 6, event_date="2026-05-01 10:00",
                  issued_at="2026-05-02 09:00", organizer="Ұйымдастырушы")
    assert os.path.getsize(out) > 2000


def test_list_available_and_verify(ctx, make):
    _, vol, _, rid = attended(make)
    assert [r["registration_id"] for r in cs.list_available(vol["id"])] == [rid]
    code = cs.issue_certificate(vol, rid)["certificate_code"]
    assert cs.verify(code.lower())["full_name"] == "Асем Сәрсенбай"
    assert cs.verify("VP-0000-NOPE") is None


def test_format_date_kz():
    assert cs.format_date_kz("2026-05-01 10:00") == "2026 жылғы 1 мамыр"


def test_http_download_own_certificate(client, make):
    _, vol, _, rid = attended(make)
    login(client, vol["email"])
    r = client.get(f"/certificates/{rid}/download")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    page = client.get("/certificates").get_data(as_text=True)
    assert "Қала саябағын тазалау" in page


def test_http_download_forbidden_for_other_and_absent(client, make):
    org, vol, eid, rid = attended(make)
    stranger = make.user()
    absent_rid = make.registration(stranger, eid, "absent")
    login(client, stranger["email"])
    assert client.get(f"/certificates/{rid}/download").status_code == 403       # басқаның сертификаты
    assert client.get(f"/certificates/{absent_rid}/download").status_code == 403  # қатыспаған
    client.post("/logout")
    assert client.get(f"/certificates/{rid}/download").status_code == 302       # кірмеген


def test_http_verify_page(client, make):
    _, vol, _, rid = attended(make)
    code = cs.issue_certificate(vol, rid)["certificate_code"]
    assert "түпнұсқа" in client.get(f"/verify/{code}").get_data(as_text=True)
    assert "табылмады" in client.get("/verify/VP-0-NOPE").get_data(as_text=True)


def test_logo_is_used_when_present(ctx, make, tmp_path, monkeypatch):
    """logo.png болса, ол PDF-ке қосылады (файл үлкейеді); бүлінген логотип PDF-ті бұзбайды."""
    from reportlab.pdfgen import canvas as rl_canvas
    kwargs = dict(code="VP-2026-LOGO", volunteer="Асем", event_title="Іс-шара",
                  event_date="2026-05-01 10:00", issued_at="2026-05-02 09:00", organizer="Ұйым")
    plain = str(tmp_path / "plain.pdf")
    cs.render_pdf(plain, **kwargs)

    from PIL import Image
    logo = tmp_path / "logo.png"
    Image.effect_noise((200, 200), 80).convert("RGB").save(logo)
    monkeypatch.setattr(cs, "find_logo", lambda: str(logo))
    with_logo = str(tmp_path / "with_logo.pdf")
    cs.render_pdf(with_logo, **kwargs)
    assert os.path.getsize(with_logo) > os.path.getsize(plain)

    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    monkeypatch.setattr(cs, "find_logo", lambda: str(bad))
    broken = str(tmp_path / "broken.pdf")
    cs.render_pdf(broken, **kwargs)
    assert open(broken, "rb").read().startswith(b"%PDF")
