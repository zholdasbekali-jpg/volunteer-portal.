"""V3 этап 7: әкімші әрекеттерінің журналы (audit log): жазу, көрсету, сүзгі, қолжетімділік."""
from app.database import get_db
from app.models import APPROVAL_APPROVED
from app.services import auth_service, audit_service
from conftest import login


def last_audit():
    return get_db().execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()


def test_role_change_is_audited(client, make):
    admin, vol = make.user("admin"), make.user("volunteer")
    login(client, admin["email"])
    client.post(f"/admin/users/{vol['id']}/role", data={"role": "organizer"})

    row = last_audit()
    assert row["actor_id"] == admin["id"]
    assert row["action"] == "user.role_changed"
    assert row["target_type"] == "user" and row["target_id"] == vol["id"]
    assert "role=organizer" in row["details"]


def test_approval_and_deletion_are_audited(ctx, client, make):
    from conftest import PASSWORD
    admin = make.user("admin")
    org_id = auth_service.register_user("Журнал Ұйымдастырушысы", "audit-org@mail.test",
                                        PASSWORD, "organizer")
    auth_service.set_approval(admin, org_id, APPROVAL_APPROVED)  # сервистік деңгейде журнал жазылмайды
    assert get_db().execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0

    login(client, admin["email"])
    client.post(f"/admin/users/{org_id}/approval", data={"approval": "rejected"})
    row = last_audit()
    assert row["action"] == "user.rejected" and row["target_id"] == org_id

    client.post(f"/admin/users/{org_id}/delete")
    row = last_audit()
    assert row["action"] == "user.deleted" and row["target_id"] == org_id


def test_audit_tab_shows_actions_and_filters(client, make):
    admin, vol = make.user("admin"), make.user("volunteer")
    login(client, admin["email"])
    client.post(f"/admin/users/{vol['id']}/role", data={"role": "organizer"})

    body = client.get("/admin/?tab=audit").get_data(as_text=True)
    assert "Пайдаланушы рөлі өзгертілді" in body
    assert "Тест Пайдаланушы 1" in body or admin["email"] in body
    assert 'name="a_action"' in body and 'value="user.role_changed"' in body
    filtered = client.get("/admin/?tab=audit&a_action=user.deleted").get_data(as_text=True)
    assert "role=organizer" not in filtered  # в таблице нет чужих записей (в select-options имена есть)


def test_non_admin_cannot_see_audit(client, make):
    vol = make.user("volunteer")
    login(client, vol["email"])
    assert client.get("/admin/?tab=audit").status_code == 403


def test_admin_event_actions_are_audited(client, make):
    admin, org = make.user("admin"), make.user("organizer")
    eid = make.event(org)
    login(client, admin["email"])
    client.post(f"/organizer/events/{eid}/cancel")
    row = last_audit()
    assert row["action"] == "event.cancelled" and row["target_type"] == "event"
    assert row["target_id"] == eid


def test_audit_service_logs_and_lists(ctx, make):
    admin = make.user("admin")
    audit_service.log(admin, "user.approved", "user", 42, "approval=approved")
    rows = audit_service.list_recent()
    assert len(rows) == 1
    assert rows[0]["actor_name"] == "Тест Пайдаланушы 1"
    assert rows[0]["action"] == "user.approved"
    assert audit_service.list_recent(action="user.deleted") == []
    assert len(audit_service.list_recent(q="approval")) == 1


def test_audit_service_rejects_unknown_action(ctx, make):
    admin = make.user("admin")
    from app.errors import ValidationError
    try:
        audit_service.log(admin, "drop_database")
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError")
