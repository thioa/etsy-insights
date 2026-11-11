from datetime import datetime

from etsy_insights.advisor_store import AdvisorStore, Source, Usage
from etsy_insights.store import Store
from tests.advisor_helpers import FakeAI, advisor_home
from tests.web_helpers import advisor_app

NOW = datetime.now().astimezone()
RESULT = {
    "summary": "Mugs look strong.",
    "recommendations": [
        {"title": "Custom mugs for couples", "category": "mug", "theme": "couples", "why": "High demand.",
         "evidence": ["custom mug"], "sources": ["S1"], "action": "List by Jan 15.", "backed": True},
        {"title": "Pet bowls for new puppies", "category": "pet bowl", "theme": "new pets", "why": "New niche.",
         "evidence": [], "sources": [], "action": "Research first.", "backed": False},
    ],
    "keyword_ideas": [
        {"keyword": "custom mug tumbler", "category": "mug", "kind": "new_niche", "reason": "Pet owners."},
        {"keyword": "custom mug", "category": "mug", "kind": "from_data", "reason": "Already strong."},
    ],
}
SOURCES = (Source("S1", "https://news.example/v", "Valentine guide"),)


def _client(home):
    return advisor_app(home, lambda key: FakeAI())[1]


def _save(home, *, result=RESULT, sources=SOURCES, status="done", cost=58):
    store = Store(home / "data" / "etsy.db")
    try:
        advisor = AdvisorStore(store)
        report_id = advisor.start_report(NOW, "claude-opus-5-5")
        usage = Usage(20000, 3000, 3, cost)
        if status == "done":
            advisor.finish_report(report_id, NOW, trend_note="- Valentine's Day soon.", trend_failed=False,
                                  sources=sources, result=result, stats={"keywords": 120, "categories": 6},
                                  usage=usage)
        elif status == "error":
            advisor.fail_report(report_id, NOW, "Claude is busy. Try again in a few minutes.", usage)
        return report_id
    finally:
        store.close()


def test_not_connected(tmp_path):
    html = _client(advisor_home(tmp_path, key=False)).get("/advisor").get_data(as_text=True)
    assert "Connect Claude" in html and "console.anthropic.com" in html and 'type="password"' in html
    assert "Save and test" in html and "Get advice" not in html


def test_ready_states(tmp_path):
    html = _client(advisor_home(tmp_path / "a")).get("/advisor").get_data(as_text=True)
    assert "…3456" in html and "Disconnect" in html and "Get advice" in html
    assert "Uses Claude Opus 5.5 and up to 5 web searches. Est. US$0.40–0.80 per run." in html
    assert "This month: 0 runs, US$0.00" in html
    assert "You have little research data yet, so most advice will be ideas rather than data." in html
    assert "data-advisor-run" in html and "data-advisor-run disabled" not in html

    html = _client(advisor_home(tmp_path / "b", catalog=False)).get("/advisor").get_data(as_text=True)
    assert "data-advisor-run disabled" in html and "Sync Printify first." in html and 'href="/printify"' in html

    home = advisor_home(tmp_path / "c")
    _save(home, status="error", cost=1000)
    html = _client(home).get("/advisor").get_data(as_text=True)
    assert "data-advisor-run disabled" in html and "You reached this month&#39;s Advisor limit (US$10.00)" in html
    assert "This month: 1 run, US$10.00" in html

    home = advisor_home(tmp_path / "d")
    app, c = advisor_app(home, lambda key: FakeAI(), spawn=lambda f: None)
    c.post("/api/advisor/run", headers={"X-App-Token": app.config["APP_TOKEN"]})
    html = c.get("/advisor").get_data(as_text=True)
    assert 'data-state="running"' in html and "data-advisor-run disabled" in html


def test_report_page(tmp_path):
    home = advisor_home(tmp_path)
    report_id = _save(home)
    c = _client(home)
    html = c.get(f"/advisor/{report_id}").get_data(as_text=True)
    assert "Summary" in html and "Mugs look strong." in html
    assert "Backed by data" in html and "Idea" in html and 'href="/catalog/mug"' in html
    assert "1.000.000" in html  # volume custom mug dari database (format angka aplikasi)
    assert 'href="https://news.example/v"' in html and 'rel="noopener noreferrer"' in html and 'target="_blank"' in html
    assert "New niche" in html and "From your data" in html
    assert 'data-idea="custom mug tumbler"' in html and "Researched" in html and ">New<" in html
    assert "What&#39;s trending" in html or "What's trending" in html
    assert "Est. cost" in html and "US$0.58" in html and "120 keywords" in html
    assert "Each idea uses 1 of your 15 daily searches. In queue now: 0" in html
    assert "Earlier reports" in html and f'href="/advisor/{report_id}"' in html
    latest = c.get("/advisor").get_data(as_text=True)
    assert "Custom mugs for couples" in latest


def test_report_escapes_ai_text(tmp_path):
    home = advisor_home(tmp_path)
    bad = "<script>alert(1)</script>"
    result = dict(RESULT, summary=bad, recommendations=[dict(RESULT["recommendations"][0], why=bad)])
    report_id = _save(home, result=result, sources=SOURCES + (Source("S2", "javascript:alert(1)", bad),))
    html = _client(home).get(f"/advisor/{report_id}").get_data(as_text=True)
    assert bad not in html and "&lt;script&gt;" in html and 'href="javascript:' not in html


def test_report_with_missing_data(tmp_path):
    home = advisor_home(tmp_path)
    result = dict(RESULT, recommendations=[dict(RESULT["recommendations"][0], category="poster",
                                                 evidence=["keyword that was removed"])])
    report_id = _save(home, result=result)
    r = _client(home).get(f"/advisor/{report_id}")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Posters" in html and "keyword that was removed" in html and "—" in html
    assert 'href="/catalog/poster"' not in html


def test_error_and_interrupted_reports(tmp_path):
    home = advisor_home(tmp_path)
    failed = _save(home, status="error", cost=12)
    html = _client(home).get(f"/advisor/{failed}").get_data(as_text=True)
    assert "Claude is busy. Try again in a few minutes." in html and "Est. cost" in html and "US$0.12" in html
    running = _save(home, status="running")
    c = _client(home)  # aplikasi dibuka ulang: laporan yang berjalan menjadi Interrupted
    assert "Interrupted" in c.get(f"/advisor/{running}").get_data(as_text=True)


def test_nav_has_advisor(tmp_path):
    html = _client(advisor_home(tmp_path)).get("/advisor").get_data(as_text=True)
    assert html.index('href="/catalog"') < html.index('href="/advisor"') < html.index('href="/printify"')
    assert 'href="/advisor" class="active"' in html


def test_unknown_report_404(tmp_path):
    assert _client(advisor_home(tmp_path)).get("/advisor/999").status_code == 404
