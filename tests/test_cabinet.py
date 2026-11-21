"""Жеке кабинет: рөлдер, профиль, құпиясөз, жиынтық сандар."""
import pytest

from app.errors import PermissionDenied, ValidationError
from app.services import auth_service, profile_service as ps
from conftest import PASSWORD, login


def test_cabinet_requires_login(client):
    r = client.get("/cabinet/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    for path in ("/cabinet/profile", "/cabinet/password"):
        assert client.post(path, data={}).status_code == 302


@pytest.mark.parametrize("role,marker", [("volunteer", "Іс-шара табу"), ("organizer", "Жаңа іс-шара"),
                                         ("admin", "Әкімші панелі")])
def test_each_role_sees_own_cabinet(client, make, role, marker):
    u = make.user(role, name="Айгүл Нұрланқызы")
    login(client, u["email"])
    page = client.get("/cabinet/").get_data(as_text=True)
    assert "Айгүл Нұрланқызы" in page and marker in page and u["email"] in page
    assert 'href="/cabinet/"' in page                      # мәзірдегі сілтеме
    if role != "volunteer":
        assert "Іс-шара табу" not in page                  # басқа рөлдің батырмалары жоқ


def test_volunteer_summary_counts(make):
    org, vol = make.user("organizer"), make.user("volunteer")
    e1, e2, e3 = make.event(org), make.event(org), make.event(org, days=-3)
    make.registration(vol, e1, "pending")
    make.registration(vol, e2, "attended")
    make.registration(vol, e3, "attended")
    s = dict(ps.cabinet_summary(vol)["stats"])
    assert s["Тіркелген іс-шара"] == 3 and s["Қатысқан"] == 2 and s["Қатысуы күтілуде"] == 1
    up = ps.cabinet_summary(vol)["upcoming"]
    assert {e["id"] for e in up} == {e1, e2}               # өткен іс-шара «жақын» тізімінде жоқ


def test_organizer_summary_counts_only_own(make):
    org, other, vol = make.user("organizer"), make.user("organizer"), make.user("volunteer")
    mine = make.event(org)
    make.event(org, status="cancelled")
    theirs = make.event(other)
    make.registration(vol, mine, "attended")
    make.registration(vol, theirs, "attended")
    s = dict(ps.cabinet_summary(org)["stats"])
    assert s["Менің іс-шараларым"] == 2 and s["Жарияланған"] == 1
    assert s["Барлық тіркелім"] == 1 and s["Қатысты"] == 1
    assert [e["id"] for e in ps.cabinet_summary(org)["upcoming"]] == [mine]


def test_admin_summary_and_permissions(make):
    admin = make.user("admin"); make.user("volunteer"); make.user("organizer")
    s = dict(ps.cabinet_summary(admin)["stats"])
    assert s["Пайдаланушы"] == 3 and s["Ерікті"] == 1 and s["Ұйымдастырушы"] == 1
    assert len(ps.cabinet_summary(admin)["latest_users"]) == 3
    with pytest.raises(PermissionDenied):
        ps.cabinet_summary(None)


def test_update_name(client, make):
    u = make.user("volunteer", name="Ескі Аты")
    login(client, u["email"])
    client.post("/cabinet/profile", data={"full_name": "  Жаңа   Аты  "}, follow_redirects=True)
    assert ps.get_profile(u)["full_name"] == "Жаңа Аты"
    for bad in ("", "А", "x" * 121):
        with pytest.raises(ValidationError):
            ps.update_name(u, bad)
    assert ps.get_profile(u)["full_name"] == "Жаңа Аты"


def test_name_is_escaped_in_cabinet(client, make):
    u = make.user("volunteer", name="<script>alert(1)</script>")
    login(client, u["email"])
    page = client.get("/cabinet/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_change_password_rules_and_effect(client, make):
    u = make.user("volunteer")
    cases = [("wrong-one1", "Newpass123", "Newpass123", "Қазіргі"),
             (PASSWORD, "Newpass123", "Other12345", "сәйкес емес"),
             (PASSWORD, "short1", "short1", "кемінде"),
             (PASSWORD, "onlyletters", "onlyletters", "цифр"),
             (PASSWORD, PASSWORD, PASSWORD, "өзгеше"),
             ("", "Newpass123", "Newpass123", "толтырыңыз")]
    for cur, new, conf, text in cases:
        with pytest.raises(ValidationError) as e:
            ps.change_password(u, cur, new, conf)
        assert text in e.value.message
    login(client, u["email"])
    r = client.post("/cabinet/password", data={"current_password": PASSWORD, "new_password": "Newpass123",
                                               "confirm_password": "Newpass123"}, follow_redirects=True)
    assert "Құпиясөз өзгертілді" in r.get_data(as_text=True)
    client.post("/logout")
    with pytest.raises(ValidationError):
        auth_service.authenticate(u["email"], PASSWORD)            # ескісі жарамсыз
    assert auth_service.authenticate(u["email"], "Newpass123")["id"] == u["id"]


def test_cabinet_actions_affect_only_current_user(client, make):
    a, b = make.user("volunteer", name="Біріншісі"), make.user("volunteer", name="Екіншісі")
    login(client, a["email"])
    client.post("/cabinet/profile", data={"full_name": "Өзгертілді", "id": b["id"], "user_id": b["id"]})
    assert ps.get_profile(b)["full_name"] == "Екіншісі" and ps.get_profile(a)["full_name"] == "Өзгертілді"
