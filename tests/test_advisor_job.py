import logging
from datetime import datetime

import pytest

from etsy_insights.advisor import AdvisorBusy, AdvisorJob, LimitReached, NoCatalog, NotConnected
from etsy_insights.advisor_ai import ClaudeBusy, ClaudeCutOff, KeyRejected
from etsy_insights.advisor_store import AdvisorStore, Usage
from etsy_insights.store import Store
from tests.advisor_helpers import ANALYSIS, KEY, TREND, FakeAI, advisor_home

NOW = datetime.now().astimezone()


def _job(home, ai, spawn=lambda f: f()):
    return AdvisorJob(home, lambda key: ai, now=lambda: NOW, spawn=spawn)


def _report(home, report_id):
    store = Store(home / "data" / "etsy.db")
    try:
        return AdvisorStore(store).report(report_id)
    finally:
        store.close()


def test_full_run_saves_report(tmp_path):
    home = advisor_home(tmp_path)
    ai = FakeAI()
    job = _job(home, ai)
    report_id = job.start()
    report = _report(home, report_id)
    assert report.status == "done" and report.stage is None and report.model == "claude-opus-5-5"
    ideas = [i["keyword"] for i in report.result["keyword_ideas"]]
    assert ideas == ["cat dad mug", "teacher necklace"]  # "custom mug" sudah dicari
    backed, idea = report.result["recommendations"]
    assert backed["backed"] is True and backed["evidence"] == ["custom mug"] and idea["backed"] is False
    assert report.usage == TREND.usage + ANALYSIS.usage
    assert report.sources == TREND.sources and report.trend_note == TREND.note and report.trend_failed is False
    assert report.stats["keywords"] > 0 and report.stats["categories"] > 0 and report.stats["dropped"]["ideas"] == 1
    status = job.status()
    assert status["state"] == "done" and status["report_id"] == report_id and status["error"] is None
    assert [c[0] for c in ai.calls] == ["check_trends", "analyze"] and ai.calls[1][2] == TREND


def test_trend_failure_continues(tmp_path):
    home = advisor_home(tmp_path)
    ai = FakeAI(trends=ClaudeBusy(usage=Usage(cost_cents=10)))
    report = _report(home, _job(home, ai).start())
    assert report.status == "done" and report.trend_failed is True and report.sources == ()
    assert report.usage.cost_cents == 10 + ANALYSIS.usage.cost_cents
    assert ai.calls[1][2] is None


def test_key_rejected_stops(tmp_path):
    home = advisor_home(tmp_path)
    ai = FakeAI(trends=KeyRejected())
    job = _job(home, ai)
    report = _report(home, job.start())
    assert report.status == "error" and report.error == KeyRejected.message
    assert [c[0] for c in ai.calls] == ["check_trends"]
    assert job.status()["state"] == "error" and job.status()["error"] == KeyRejected.message


def test_analysis_error_records_cost(tmp_path):
    home = advisor_home(tmp_path)
    report = _report(home, _job(home, FakeAI(analysis=ClaudeCutOff(usage=Usage(cost_cents=40)))).start())
    assert report.status == "error" and report.error == ClaudeCutOff.message
    assert report.usage.cost_cents == 40 + TREND.usage.cost_cents
    assert report.trend_note == TREND.note and report.sources == TREND.sources


def test_start_guards(tmp_path):
    with pytest.raises(NotConnected) as caught:
        _job(advisor_home(tmp_path / "a", key=False), FakeAI()).start()
    assert caught.value.status == 400 and caught.value.message == "Connect Claude first."
    with pytest.raises(NoCatalog) as caught:
        _job(advisor_home(tmp_path / "b", catalog=False), FakeAI()).start()
    assert caught.value.status == 400 and caught.value.message == "Sync Printify first."

    home = advisor_home(tmp_path / "c")
    store = Store(home / "data" / "etsy.db")
    advisor = AdvisorStore(store)
    advisor.fail_report(advisor.start_report(NOW, "claude-opus-5-5"), NOW, "x", Usage(cost_cents=1000))
    store.close()
    with pytest.raises(LimitReached) as caught:
        _job(home, FakeAI()).start()
    assert caught.value.status == 403 and "US$10.00" in caught.value.message
    (home / "config.toml").write_text("advisor_batas_bulanan_usd = 0\n", encoding="utf-8")
    assert _job(home, FakeAI()).start() > 0

    waiting = _job(advisor_home(tmp_path / "d"), FakeAI(), spawn=lambda f: None)
    waiting.start()
    with pytest.raises(AdvisorBusy) as caught:
        waiting.start()
    assert caught.value.status == 409 and caught.value.message == "Advice is already running."
    status = waiting.status()
    assert status["state"] == "running" and status["stage"] is None and status["elapsed_seconds"] == 0


def test_interrupted_on_restart(tmp_path):
    home = advisor_home(tmp_path)
    report_id = _job(home, FakeAI(), spawn=lambda f: None).start()
    job = _job(home, FakeAI())
    assert _report(home, report_id).status == "interrupted"
    assert job.status()["state"] == "idle"


def test_unexpected_exception(tmp_path, caplog):
    home = advisor_home(tmp_path)
    with caplog.at_level(logging.ERROR):
        report = _report(home, _job(home, FakeAI(analysis=RuntimeError(f"boom {KEY}"))).start())
    assert report.status == "error" and report.error == "Something went wrong. See the log for details."
    assert "boom" in caplog.text and KEY not in caplog.text


def test_step1_stream_drop_continues(tmp_path):
    import json
    from etsy_insights.advisor_ai import AdvisorAI
    from tests.advisor_helpers import ANSWER
    from tests.anthropic_fake import FakeAnthropic, Truncated, message_events, stream, text_block
    home = advisor_home(tmp_path)
    with FakeAnthropic() as fake:
        fake.queue("POST", "/v1/messages", Truncated(message_events([text_block("- partial")])[:4]),
                   stream([text_block(json.dumps(ANSWER))]))
        job = AdvisorJob(home, lambda key: AdvisorAI(key, base_url=fake.url, trust_env=False, max_retries=0),
                         now=lambda: NOW, spawn=lambda f: f())
        report = _report(home, job.start())
    assert report.status == "done" and report.trend_failed is True
    assert [i["keyword"] for i in report.result["keyword_ideas"]] == ["cat dad mug", "teacher necklace"]


def test_report_records_served_model(tmp_path):
    from dataclasses import replace
    home = advisor_home(tmp_path)
    ai = FakeAI(analysis=replace(ANALYSIS, model="claude-opus-4-8"))
    assert _report(home, _job(home, ai).start()).model == "claude-opus-4-8"
