from datetime import datetime, timedelta

import pytest
from openpyxl import load_workbook

from etsy_insights.store import Store
from etsy_insights.web import create_app
from tests.web_helpers import TOKEN, FakeRunner, client, seeded_home

H = {"X-App-Token": TOKEN}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ETSY_INSIGHTS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    home = seeded_home(tmp_path / "home")
    runner = FakeRunner()
    quits = []
    app = create_app(home, token=TOKEN, runner=runner, on_quit=lambda: quits.append(1))
    return home, runner, quits, client(app)


def test_ping_and_status(setup):
    home, runner, quits, c = setup
    assert c.get("/api/ping").get_json() == {"ok": True, "app": "etsy-insights"}
    st = c.get("/api/status").get_json()
    assert st["today"]["limit"] == 15 and st["collected"] > 400 and st["account"]["state"] == "safe"
    assert st["can_start"] is True and st["runner"]["running"] is False


def test_post_requires_token_host_and_origin(setup):
    home, runner, quits, c = setup
    assert c.post("/api/session/start", json={}).status_code == 403
    assert c.post("/api/session/start", json={}, headers={**H, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/session/start", json={}, headers=H, base_url="http://evil.example:8765").status_code == 403
    assert c.get("/api/ping", base_url="http://evil.example:8765").status_code == 403
    assert runner.started == []
    assert c.post("/api/session/start", json={"test_run": True},
                  headers={**H, "Origin": "http://127.0.0.1:8765"}).status_code == 200
    assert runner.started == [{"test_run": True, "ignore_cooldown": False}]


def test_start_blocked_by_cooldown_unless_yes(setup):
    home, runner, quits, c = setup
    s = Store(home / "data" / "etsy.db")
    now = datetime.now().astimezone()
    sid = s.start_session(now)
    s.end_session(sid, now, "tanda_bahaya", now + timedelta(hours=24))
    s.close()
    r = c.post("/api/session/start", json={}, headers=H)
    assert r.status_code == 409 and "Cooldown" in r.get_json()["error"]
    assert c.post("/api/session/start", json={"ignore_cooldown": True, "confirm": "yes"}, headers=H).status_code == 409
    assert c.post("/api/session/start", json={"ignore_cooldown": True, "confirm": "YES"}, headers=H).status_code == 200


def test_start_refused_when_runner_busy(setup):
    home, runner, quits, c = setup
    runner.running = True
    assert c.post("/api/session/start", json={}, headers=H).status_code == 409


def test_keywords_and_settings_api(setup):
    home, runner, quits, c = setup
    assert c.post("/api/keywords/add", json={"text": "Tote Bag\nmug"}, headers=H).get_json()["added"] == ["tote bag", "mug"]
    assert c.post("/api/keywords/remove", json={"keyword": "mug"}, headers=H).status_code == 200
    assert c.post("/api/keywords/remove", json={"keyword": "sweatshirt"}, headers=H).status_code == 409
    assert c.post("/api/keywords/prioritize", json={"keyword": "gift for her"}, headers=H).status_code == 200
    assert c.post("/api/keywords/prioritize", json={"keyword": "zzz"}, headers=H).status_code == 404
    r = c.post("/api/settings", json={"kuota_harian": "99"}, headers=H)
    assert r.status_code == 400 and "kuota_harian" in r.get_json()["errors"]


def test_quit_confirms_running_session(setup):
    home, runner, quits, c = setup
    runner.running = True
    assert c.post("/api/quit", json={}, headers=H).status_code == 409 and quits == []
    assert c.post("/api/quit", json={"confirm": True}, headers=H).status_code == 200
    assert runner.stopped and quits == [1]


def test_download_excel(setup, tmp_path):
    home, runner, quits, c = setup
    r = c.get("/download/excel")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    files = list((tmp_path / "Documents" / "Etsy Insights").glob("opportunities-*.xlsx"))
    assert len(files) == 1 and load_workbook(files[0]).sheetnames[0] == "Opportunities"


def test_frame_and_referrer_headers(setup):
    home, runner, quits, c = setup
    for path in ("/", "/settings", "/api/status"):
        resp = c.get(path)
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]
        assert resp.headers["Referrer-Policy"] == "no-referrer"


def test_status_reuses_queue_ranking_until_data_changes(setup, monkeypatch):
    import etsy_insights.planner as planner
    from etsy_insights.config import Config
    home, runner, quits, c = setup
    store = Store(home / "data" / "etsy.db")
    expected = len(planner.upcoming(store, Config(), limit=10**9))
    store.close()
    calls = []
    real = planner.score_all
    monkeypatch.setattr(planner, "score_all", lambda rows, cfg: calls.append(1) or real(rows, cfg))
    assert c.get("/api/status").get_json()["queue"] == expected
    c.get("/api/status")
    c.get("/")
    assert len(calls) == 1
    assert c.post("/api/keywords/add", json={"text": "brand new keyword"}, headers=H).status_code == 200
    assert c.get("/api/status").get_json()["queue"] == expected + 1


def test_status_shows_local_time(setup, monkeypatch):
    import time
    from datetime import timezone
    home, runner, quits, c = setup
    monkeypatch.setenv("TZ", "Asia/Jakarta")
    time.tzset()
    try:
        store = Store(home / "data" / "etsy.db")
        sid = store.start_session(datetime(2026, 11, 11, 5, 29, tzinfo=timezone.utc))
        store.end_session(sid, datetime(2026, 11, 11, 5, 40, tzinfo=timezone.utc), "no_quota", None)
        store.close()
        last = c.get("/api/status").get_json()["last_session"]
        assert last["started_text"] == "2026-11-11 12:29"
        assert "2026-11-11 12:29" in c.get("/").get_data(as_text=True)
    finally:
        monkeypatch.undo()
        time.tzset()


def test_status_reports_start_error(tmp_path, monkeypatch):
    from etsy_insights.runner import RunnerStatus
    monkeypatch.setenv("HOME", str(tmp_path))
    home = seeded_home(tmp_path / "home")
    runner = FakeRunner()
    runner.status = lambda tail=20: RunnerStatus(False, None, None, 0, None, (), False, error_code=1,
                                                 error_tail=("Google Chrome was not found.",))
    c = client(create_app(home, token=TOKEN, runner=runner))
    st = c.get("/api/status").get_json()
    assert st["runner"]["error_code"] == 1 and st["runner"]["error_tail"] == ["Google Chrome was not found."]
    html = c.get("/").get_data(as_text=True)
    assert "Google Chrome was not found." in html and 'href="/log"' in html and "Open log" in html
