from datetime import datetime, timedelta, timezone

from etsy_insights.advisor_store import AdvisorStore, Source, Usage
from etsy_insights.store import Store

WIB = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 11, 10, 0, tzinfo=WIB)


def _store(tmp_path):
    return Store(tmp_path / "data" / "etsy.db")


def test_report_lifecycle(tmp_path):
    store = _store(tmp_path)
    advisor = AdvisorStore(store)
    report_id = advisor.start_report(NOW, "claude-opus-5-5")
    report = advisor.report(report_id)
    assert report.status == "running" and report.model == "claude-opus-5-5" and report.finished_at is None
    advisor.set_stage(report_id, "analyzing")
    assert advisor.report(report_id).stage == "analyzing"
    sources = (Source("S1", "https://a.example/x", "A"), Source("S2", "https://b.example/y", "B"))
    result = {"summary": "x", "recommendations": [], "keyword_ideas": [{"keyword": "dog mom tumbler"}]}
    advisor.finish_report(report_id, NOW + timedelta(minutes=2), trend_note="Valentine's Day soon.",
                          trend_failed=False, sources=sources, result=result, stats={"keywords": 3},
                          usage=Usage(1000, 200, 2, 9))
    done = advisor.report(report_id)
    assert done.status == "done" and done.stage is None
    assert done.sources == sources and done.result == result and done.stats == {"keywords": 3}
    assert done.trend_note == "Valentine's Day soon." and done.trend_failed is False
    assert done.usage == Usage(1000, 200, 2, 9)
    assert done.finished_at == NOW + timedelta(minutes=2) and done.started_at == NOW
    assert advisor.report(999) is None


def test_fail_keeps_cost(tmp_path):
    advisor = AdvisorStore(_store(tmp_path))
    report_id = advisor.start_report(NOW, "claude-opus-5-5")
    advisor.fail_report(report_id, NOW, "Claude is busy.", Usage(cost_cents=12), trend_failed=True)
    report = advisor.report(report_id)
    assert report.status == "error" and report.error == "Claude is busy."
    assert report.usage.cost_cents == 12 and report.trend_failed is True and report.result is None


def test_mark_interrupted_and_order(tmp_path):
    advisor = AdvisorStore(_store(tmp_path))
    first = advisor.start_report(NOW, "claude-opus-5-5")
    second = advisor.start_report(NOW + timedelta(minutes=1), "claude-opus-5-5")
    assert advisor.mark_interrupted() == 2
    assert {advisor.report(first).status, advisor.report(second).status} == {"interrupted"}
    assert [r.id for r in advisor.reports()] == [second, first]
    assert advisor.mark_interrupted() == 0


def test_month_spend_uses_local_month(tmp_path):
    advisor = AdvisorStore(_store(tmp_path))
    october = advisor.start_report(datetime(2026, 10, 31, 23, 30, tzinfo=WIB), "claude-opus-5-5")
    advisor.fail_report(october, datetime(2026, 10, 31, 23, 31, tzinfo=WIB), "x", Usage(cost_cents=50))
    november = advisor.start_report(datetime(2026, 11, 1, 0, 10, tzinfo=WIB), "claude-opus-5-5")
    advisor.fail_report(november, datetime(2026, 11, 1, 0, 11, tzinfo=WIB), "x", Usage(cost_cents=30))
    assert advisor.month_spend(NOW) == (1, 30)
    assert advisor.month_spend(datetime(2026, 10, 15, 12, 0, tzinfo=WIB)) == (1, 50)


def test_old_database_gets_table(tmp_path):
    store = _store(tmp_path)
    store.connection.execute("DROP TABLE advisor_reports")
    store.close()
    store = _store(tmp_path)
    assert AdvisorStore(store).reports() == []


def test_usage_add():
    assert Usage(1, 2, 3, 4) + Usage(10, 20, 30, 40) == Usage(11, 22, 33, 44)
