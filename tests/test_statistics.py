"""FR-08: статистика есептеуі және Matplotlib графиктері."""
import pytest

from app.errors import NotFound
from app.services import statistics_service as ss
from conftest import login


def populate(make):
    org1, org2 = make.user("organizer"), make.user("organizer")
    v1, v2, v3 = make.user(), make.user(), make.user()
    e1 = make.event(org1, capacity=4, days=-3)
    e2 = make.event(org1, capacity=2, days=4)
    e3 = make.event(org2, capacity=10, days=6)
    make.registration(v1, e1, "attended")
    make.registration(v2, e1, "absent")
    make.registration(v1, e2)
    make.registration(v2, e2)
    make.registration(v3, e3)
    return org1, org2, (e1, e2, e3)


def test_summary_platform(ctx, make):
    populate(make)
    s = ss.get_summary()
    assert s["events_total"] == 3
    assert s["volunteers_total"] == 3
    assert s["registrations_total"] == 5
    assert s["attended_total"] == 1
    # толу = 5 тіркелім / (4+2+10) сыйымдылық = 31.25 %
    assert s["fill_rate"] == 31.2 or s["fill_rate"] == 31.3


def test_summary_scoped_to_organizer(ctx, make):
    org1, org2, _ = populate(make)
    s1 = ss.get_summary(org1["id"])
    assert (s1["events_total"], s1["registrations_total"], s1["attended_total"]) == (2, 4, 1)
    assert s1["fill_rate"] == round(4 * 100 / 6, 1)
    s2 = ss.get_summary(org2["id"])
    assert (s2["events_total"], s2["registrations_total"]) == (1, 1)


def test_event_stats(ctx, make):
    org1, _, (e1, e2, _) = populate(make)
    stats = {s["id"]: s for s in ss.get_event_stats(org1["id"])}
    assert set(stats) == {e1, e2}
    assert stats[e2]["registered"] == 2 and stats[e2]["fill_rate"] == 100.0
    assert stats[e1]["attended"] == 1


def test_empty_database_statistics(ctx):
    s = ss.get_summary()
    assert s == {"events_total": 0, "volunteers_total": 0, "registrations_total": 0,
                 "attended_total": 0, "fill_rate": 0.0}
    for name in ss.CHART_NAMES:               # бос деректерде де график құлаймайды
        assert ss.render_chart(name).startswith(b"\x89PNG")


@pytest.mark.parametrize("name", ss.CHART_NAMES)
def test_charts_are_png(ctx, make, name):
    populate(make)
    assert ss.render_chart(name).startswith(b"\x89PNG")


def test_unknown_chart_rejected(ctx):
    with pytest.raises(NotFound):
        ss.render_chart("../../etc/passwd")


def test_http_statistics_page_and_charts(client, make):
    org1, _, _ = populate(make)
    login(client, org1["email"])
    page = client.get("/statistics").get_data(as_text=True)
    assert "Статистика" in page and "/statistics/chart/summary.png" in page
    for name in ss.CHART_NAMES:
        r = client.get(f"/statistics/chart/{name}.png")
        assert r.status_code == 200 and r.mimetype == "image/png" and r.data.startswith(b"\x89PNG")
    assert client.get("/statistics/chart/nope.png").status_code == 404


def test_statistics_access_control(client, make):
    vol = make.user("volunteer")
    assert client.get("/statistics/chart/summary.png").status_code == 302   # кірмеген
    login(client, vol["email"])
    assert client.get("/statistics").status_code == 403
    assert client.get("/statistics/chart/summary.png").status_code == 403
