from datetime import timedelta

from etsy_insights.config import Config
from etsy_insights.models import DangerSignal, NotLoggedIn
from etsy_insights.session import StopReason, format_summary, run_session
from etsy_insights.store import Store
from tests.helpers import T0, FakeClock, FakePage, make_deps


def setup(*kws, **page_kw):
    clock = FakeClock(T0, interrupt_on_sleep=page_kw.pop("interrupt_on_sleep", None))
    store = Store(":memory:")
    store.sync_user_keywords(kws, T0)
    return clock, store, FakePage(clock, **page_kw)


def test_stops_at_max_keywords_without_trailing_sleep():
    clock, store, page = setup("a", "b", "c", "d", "e")
    s = run_session(make_deps(store, page, clock, Config(jeda_antar_keyword_detik=(20, 20))), max_keywords=3)
    assert (s.stop_reason, s.checked, s.succeeded) == (StopReason.QUOTA, 3, 3)
    assert page.searched == ["a", "b", "c"] and clock.sleeps == [20, 20] and len(page.dwells) == 3
    assert store.status_counts() == {"done": 3, "pending": 2}


def test_related_keywords_follow_user_keywords():
    clock, store, page = setup("a", "b", related={"a": ("a1", "a2")})
    s = run_session(make_deps(store, page, clock), max_keywords=4)
    assert page.searched == ["a", "b", "a1", "a2"] and s.new_keywords == 2


def test_queue_empty():
    clock, store, page = setup("a")
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, clock.sleeps) == (StopReason.QUEUE_EMPTY, 1, [])


def test_captcha_sets_cooldown_and_blocks_next_run():
    clock, store, page = setup("a", "b", "c", outcomes={"b": "captcha"})
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.DANGER and s.danger.kind == "captcha"
    assert s.cooldown_until == clock.now() + timedelta(hours=24)
    assert (store.get("b").status, store.get("b").fail_count) == ("pending", 0)
    page2 = FakePage(clock)
    assert run_session(make_deps(store, page2, clock)).stop_reason is StopReason.COOLDOWN and page2.opened == 0
    assert run_session(make_deps(store, page2, clock), ignore_cooldown=True).stop_reason is not StopReason.COOLDOWN


def test_danger_right_after_open():
    clock, store, page = setup("a", danger_on_open=DangerSignal("login", "/signin"))
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked) == (StopReason.DANGER, 0) and s.cooldown_until is not None


def test_three_consecutive_failures_stop_without_cooldown():
    clock, store, page = setup("a", "b", "c", "d", outcomes={"a": "parse_error", "b": "timeout", "c": "parse_error"})
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.failed, s.cooldown_until) == (StopReason.FAILURES, 3, None)
    assert page.searched == ["a", "b", "c"]
    assert [store.get(k).fail_count for k in "abc"] == [1, 1, 1] and store.get("a").status == "pending"


def test_success_resets_failure_streak():
    clock, store, page = setup(*"abcdef", outcomes={k: "parse_error" for k in "abde"})
    s = run_session(make_deps(store, page, clock), max_keywords=6)
    assert (s.stop_reason, s.failed, s.succeeded) == (StopReason.QUOTA, 4, 2)


def test_no_data_is_not_a_failure():
    clock, store, page = setup("a", outcomes={"a": "no_data"})
    s = run_session(make_deps(store, page, clock))
    assert (s.no_data, s.failed, store.get("a").status) == (1, 0, "no_data")


def test_browser_closed():
    clock, store, page = setup("a", "b", "c", outcomes={"b": "closed"})
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked) == (StopReason.BROWSER_CLOSED, 2)
    assert (store.get("b").status, store.get("b").fail_count) == ("pending", 0)


def test_interrupt_during_sleep():
    clock, store, page = setup("a", "b", interrupt_on_sleep=1)
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked) == (StopReason.INTERRUPTED, 1)
    assert store.status_counts() == {"done": 1, "pending": 1}
    assert store.last_session()["stop_reason"] == "dihentikan"


def test_interrupt_during_search():
    clock, store, page = setup("a", outcomes={"a": "interrupt"})
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.INTERRUPTED and store.status_counts() == {"pending": 1}


def test_not_logged_in():
    clock, store, page = setup("a", open_error=NotLoggedIn())
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, s.cooldown_until) == (StopReason.NOT_LOGGED_IN, 0, None)


def test_quota_used_up_and_partially_used():
    clock, store, page = setup("a", "b", "c")
    sid = store.start_session(T0)
    for _ in range(48):
        store.increment_checked(sid)
    store.end_session(sid, T0, "kuota_tercapai", None)
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, s.quota_left) == (StopReason.QUOTA, 2, 0)
    page2 = FakePage(clock)
    s2 = run_session(make_deps(store, page2, clock))
    assert s2.stop_reason is StopReason.NO_QUOTA and page2.opened == 0


def test_duration_limit():
    clock, store, page = setup(*"abcde")
    cfg = Config(jeda_antar_keyword_detik=(900, 900), waktu_baca_detik=(5, 5))
    s = run_session(make_deps(store, page, clock, cfg))
    assert (s.stop_reason, s.checked, clock.sleeps) == (StopReason.DURATION, 3, [900, 900, 900])


def test_long_break_schedule():
    clock, store, page = setup(*"abcd")
    cfg = Config(jeda_antar_keyword_detik=(20, 20), istirahat_setiap=(2, 2), istirahat_detik=(200, 200))
    run_session(make_deps(store, page, clock, cfg))
    assert clock.sleeps == [20, 200, 20]


def test_format_summary():
    clock, store, page = setup("a", "b", "c", outcomes={"c": "captcha"})
    text = format_summary(run_session(make_deps(store, page, clock)))
    assert "Keyword dicek: 3" in text and "Sisa kuota hari ini: 47" in text and "Masa pendinginan sampai" in text


def test_unexpected_error_returns_keyword_and_closes_session():
    import pytest
    clock, store, page = setup("a")

    def boom(keyword):
        raise RuntimeError("tak terduga")
    page.search = boom
    with pytest.raises(RuntimeError):
        run_session(make_deps(store, page, clock))
    assert store.status_counts() == {"pending": 1} and store.last_session()["stop_reason"] == "error"
