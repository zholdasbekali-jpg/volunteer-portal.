"""V3 этап 5: одобрение организаторов администратором (регистрация, доступ, админ, письмо)."""
import pytest

from app.database import get_db
from app.errors import PermissionDenied, ValidationError
from app.models import APPROVAL_APPROVED, APPROVAL_PENDING, APPROVAL_REJECTED
from app.services import auth_service, event_service
from conftest import PASSWORD, login, when


def register_org(client, email, name="Жаңа Ұйымдастырушы"):
    return client.post("/register", data={"full_name": name, "email": email,
                                          "password": PASSWORD, "role": "organizer"},
                       follow_redirects=True)


def approval(user_id):
    return get_db().execute("SELECT approval FROM users WHERE id=?", (user_id,)).fetchone()["approval"]


def event_form():
    return {"title": "Жаңа іс-шара", "description": "Сипаттама", "city": "Қызылорда",
            "location": "Орталық көше, 1", "event_date": when(5).replace(" ", "T"),
            "capacity": "10", "hours": "3", "category": "ecology"}


def make_pending_org(email="pending@mail.test"):
    uid = auth_service.register_user("Күтудегі Ұйымдастырушы", email, PASSWORD, "organizer")
    return auth_service.get_user(uid)


def test_self_registration_sets_approval_status(ctx, client, make):
    register_org(client, "self-org@mail.test")
    org = get_db().execute("SELECT approval, role FROM users WHERE email=?",
                           ("self-org@mail.test",)).fetchone()
    assert org["role"] == "organizer" and org["approval"] == APPROVAL_PENDING
    auth_service.register_user("Жаңа Ерікті", "self-vol@mail.test", PASSWORD, "volunteer")
    assert approval(get_db().execute("SELECT id FROM users WHERE email=?",
                                     ("self-vol@mail.test",)).fetchone()["id"]) == APPROVAL_APPROVED


def test_pending_organizer_can_login_but_sees_waiting_page(ctx, client):
    make_pending_org()
    response = login(client, "pending@mail.test")
    assert response.status_code == 200
    assert "мақұлдануды күтудесіз" in response.get_data(as_text=True)
    direct = client.post("/login", data={"email": "pending@mail.test", "password": PASSWORD})
    assert direct.status_code == 302 and "/pending-approval" in direct.headers["Location"]


def test_pending_organizer_cannot_manage_or_create_events(ctx, client):
    org = make_pending_org()
    with pytest.raises(PermissionDenied):
        event_service.create_event(org, event_form())
    login(client, "pending@mail.test")
    assert "/pending-approval" in client.get("/organizer").headers["Location"]
    assert "/pending-approval" in client.post("/organizer/events/new", data=event_form()).headers["Location"]


def test_admin_approves_and_sends_email(app, ctx, client, make):
    admin, org = make.user("admin"), make_pending_org()
    login(client, admin["email"])
    response = client.post(f"/admin/users/{org['id']}/approval",
                           data={"approval": APPROVAL_APPROVED}, follow_redirects=True)
    assert response.status_code == 200
    assert "Ұйымдастырушы мақұлдалды." in response.get_data(as_text=True)
    assert approval(org["id"]) == APPROVAL_APPROVED
    mails = [m for m in app.extensions["mail_outbox"] if m["kind"] == "approval"]
    assert len(mails) == 1 and mails[0]["to"] == "pending@mail.test"


def test_approved_organizer_can_create_event(client, ctx):
    org = make_pending_org()
    auth_service.set_approval({"id": 1, "role": "admin"}, org["id"], APPROVAL_APPROVED)
    login(client, "pending@mail.test")
    assert client.get("/organizer").status_code == 200
    response = client.post("/organizer/events/new", data=event_form(), follow_redirects=True)
    assert response.status_code == 200
    assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_reject_and_non_admin_cannot_approve(ctx, client, make):
    admin, org, vol = make.user("admin"), make_pending_org(), make.user("volunteer")
    login(client, vol["email"])
    assert client.post(f"/admin/users/{org['id']}/approval",
                       data={"approval": APPROVAL_APPROVED}).status_code == 403
    # один логин на тест: дальше проверяем сервис от имени админа
    auth_service.set_approval(admin, org["id"], APPROVAL_REJECTED)
    assert approval(org["id"]) == APPROVAL_REJECTED
    assert not event_service.can_manage({"organizer_id": org["id"]}, org)


def test_admin_role_promotion_approves_organizer(client, make):
    admin, vol = make.user("admin"), make.user("volunteer")
    login(client, admin["email"])
    client.post(f"/admin/users/{vol['id']}/role", data={"role": "organizer"})
    row = get_db().execute("SELECT role, approval FROM users WHERE id=?", (vol["id"],)).fetchone()
    assert row["role"] == "organizer" and row["approval"] == APPROVAL_APPROVED


def test_admin_filters_users_by_approval(ctx, client, make):
    admin = make.user("admin")
    pending = make_pending_org("filter-pending@mail.test")
    approved = make_pending_org("filter-approved@mail.test")
    auth_service.set_approval(admin, approved["id"], APPROVAL_APPROVED)
    login(client, admin["email"])

    body = client.get("/admin/?tab=users&u_approval=pending").get_data(as_text=True)
    assert "Күтудегі Ұйымдастырушы" in body
    assert 'value="pending" selected' in body
    body = client.get("/admin/?tab=users&u_approval=approved").get_data(as_text=True)
    assert len([line for line in body.splitlines() if "mail.test" in line]) >= 1


def test_approval_service_validates(ctx, make):
    admin, vol, org = make.user("admin"), make.user("volunteer"), make_pending_org()
    with pytest.raises(PermissionDenied):
        auth_service.set_approval(vol, org["id"], APPROVAL_APPROVED)
    with pytest.raises(ValidationError):
        auth_service.set_approval(admin, org["id"], "hack")
    with pytest.raises(ValidationError):
        auth_service.set_approval(admin, vol["id"], APPROVAL_APPROVED)
    with pytest.raises(Exception):
        auth_service.set_approval(admin, 999999, APPROVAL_APPROVED)
    assert approval(org["id"]) == APPROVAL_PENDING
