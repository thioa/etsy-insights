from datetime import datetime

from etsy_insights.advisor_ai import ClaudeUnreachable, KeyRejected
from etsy_insights.advisor_store import AdvisorStore, Usage
from etsy_insights.store import Store
from tests.advisor_helpers import KEY, FakeAI, advisor_home
from tests.web_helpers import TOKEN, advisor_app

H = {"X-App-Token": TOKEN}


def _app(home, ai=None, **kwargs):
    ai = ai or FakeAI()
    return advisor_app(home, lambda key: ai, **kwargs)


def test_save_key_paths(tmp_path):
    home = advisor_home(tmp_path, key=False)
    path = home / "anthropic-key"
    bodies = []

    def post(ai, key):
        _, c = _app(home, ai)
        r = c.post("/api/advisor/key", json={"key": key}, headers=H)
        bodies.append(r.get_data(as_text=True))
        return r

    r = post(FakeAI(), "  ")
    assert r.status_code == 400 and r.get_json()["error"] == "Paste your Anthropic API key."
    r = post(FakeAI(), "hello")
    assert r.status_code == 400 and r.get_json()["error"] == "That does not look like an Anthropic API key."
    r = post(FakeAI(key_check=KeyRejected()), KEY)
    assert r.status_code == 400 and r.get_json()["error"] == KeyRejected.message and not path.exists()
    r = post(FakeAI(key_check=ClaudeUnreachable()), KEY)
    assert r.status_code == 200 and r.get_json()["warning"] == "Saved, but Anthropic could not be reached to test it."
    assert path.exists()
    path.unlink()
    r = post(FakeAI(), f" {KEY}\n")
    assert r.status_code == 200 and r.get_json() == {"hint": "…3456"} and path.exists()
    assert not [b for b in bodies if KEY in b]


def test_disconnect(tmp_path):
    home = advisor_home(tmp_path)
    _, c = _app(home)
    assert c.post("/api/advisor/disconnect", headers=H).get_json() == {"ok": True}
    assert not (home / "anthropic-key").exists()


def test_run_and_status(tmp_path):
    home = advisor_home(tmp_path / "a")
    _, c = _app(home)
    r = c.post("/api/advisor/run", headers=H)
    assert r.status_code == 202 and r.get_json()["report_id"] > 0
    status = c.get("/api/advisor/status", headers=H).get_json()
    assert status["state"] == "done" and status["report_id"] == r.get_json()["report_id"]
    assert set(status) == {"state", "stage", "elapsed_seconds", "report_id", "error"}

    _, c = _app(advisor_home(tmp_path / "b", key=False))
    r = c.post("/api/advisor/run", headers=H)
    assert r.status_code == 400 and r.get_json()["error"] == "Connect Claude first."
    _, c = _app(advisor_home(tmp_path / "c", catalog=False))
    r = c.post("/api/advisor/run", headers=H)
    assert r.status_code == 400 and r.get_json()["error"] == "Sync Printify first."

    home = advisor_home(tmp_path / "d")
    store = Store(home / "data" / "etsy.db")
    advisor = AdvisorStore(store)
    now = datetime.now().astimezone()
    advisor.fail_report(advisor.start_report(now, "claude-opus-5-5"), now, "x", Usage(cost_cents=2000))
    store.close()
    _, c = _app(home)
    r = c.post("/api/advisor/run", headers=H)
    assert r.status_code == 403 and "Advisor limit" in r.get_json()["error"]

    _, c = _app(advisor_home(tmp_path / "e"), spawn=lambda f: None)
    assert c.post("/api/advisor/run", headers=H).status_code == 202
    r = c.post("/api/advisor/run", headers=H)
    assert r.status_code == 409 and r.get_json()["error"] == "Advice is already running."


def test_add_only_report_ideas(tmp_path):
    home = advisor_home(tmp_path)
    _, c = _app(home)
    report_id = c.post("/api/advisor/run", headers=H).get_json()["report_id"]
    r = c.post("/api/advisor/add", json={"report_id": report_id, "keywords": ["Cat Dad Mug", "free money"]},
               headers=H)
    assert r.status_code == 200 and r.get_json()["added"] == ["cat dad mug"]
    assert r.get_json()["statuses"] == {"cat dad mug": "in_queue", "teacher necklace": "new"}
    text = (home / "keywords.txt").read_text(encoding="utf-8")
    assert "cat dad mug" in text and "free money" not in text
    again = c.post("/api/advisor/add", json={"report_id": report_id, "keywords": ["cat dad mug"]}, headers=H)
    assert again.status_code == 200 and again.get_json()["added"] == []
    missing = c.post("/api/advisor/add", json={"report_id": 999, "keywords": ["cat dad mug"]}, headers=H)
    assert missing.status_code == 404 and missing.get_json()["error"] == "Report not found."
    bad = c.post("/api/advisor/add", json={"report_id": report_id, "keywords": "cat dad mug"}, headers=H)
    assert bad.status_code == 400 and bad.get_json()["error"] == "Choose at least one keyword."


def test_token_required(tmp_path):
    _, c = _app(advisor_home(tmp_path))
    assert c.post("/api/advisor/run").status_code == 403
    assert c.post("/api/advisor/key", json={"key": KEY}).status_code == 403
    assert c.get("/api/advisor/status").status_code == 403
    assert c.get("/api/advisor/status", headers=H).status_code == 200
