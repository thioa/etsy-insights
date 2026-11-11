from datetime import timedelta

from etsy_insights.store import Store, normalize_keyword, read_keywords_file
from tests.helpers import T0, make_metrics, make_raw


def new_store(*kws):
    s = Store(":memory:")
    s.sync_user_keywords(kws, T0)
    return s


def test_normalize():
    assert normalize_keyword("  Boho   Wall ART ") == "boho wall art" and normalize_keyword("   ") == ""


def test_read_keywords_file_messy(tmp_path):
    p = tmp_path / "keywords.txt"
    p.write_bytes("﻿Boho Wall Art\r\n\r\n# komentar\r\nboho wall art\r\n  macrame  \r\n".encode())
    assert read_keywords_file(p) == ["boho wall art", "macrame"]
    assert read_keywords_file(tmp_path / "tidak-ada.txt") == []


def test_sync_adds_once():
    s = Store(":memory:")
    assert s.sync_user_keywords(["a", "b"], T0) == 2 and s.sync_user_keywords(["A"], T0) == 0


def test_sync_promotes_related_to_user():
    s = new_store("a")
    s.add_related(s.get("a").id, ["b"], 10, 2, T0)
    assert s.sync_user_keywords(["b"], T0) == 1
    b = s.get("b")
    assert (b.source, b.depth, b.parent_keyword) == ("user", 0, None)


def test_queue_order_user_first_then_by_depth():
    s = new_store("a", "b")
    s.add_related(s.get("a").id, ["a1"], 10, 2, T0 + timedelta(seconds=1))
    s.add_related(s.get("a1").id, ["a2"], 10, 2, T0 + timedelta(seconds=2))
    s.add_related(s.get("b").id, ["b1"], 10, 2, T0 + timedelta(seconds=3))
    assert [q.keyword for q in s.pending_queue()] == ["a", "b", "a1", "b1", "a2"]


def test_add_related_respects_max_count_and_depth():
    s = new_store("a")
    assert s.add_related(s.get("a").id, ["x", "y", "z"], 2, 2, T0) == 2
    s.add_related(s.get("x").id, ["x1"], 10, 2, T0)
    assert s.get("x1").depth == 2 and s.add_related(s.get("x1").id, ["x2"], 10, 2, T0) == 0


def test_add_related_skips_self_existing_blank():
    s = new_store("a", "b")
    assert s.add_related(s.get("a").id, ["A", " a ", "", "b", "new", "NEW"], 10, 2, T0) == 1
    assert s.get("new").parent_keyword == "a"


def test_next_keyword_excludes_ids():
    s = new_store("a", "b")
    assert s.next_keyword(T0, 30, exclude_ids={s.get("a").id}).keyword == "b"


def test_recheck_only_when_no_pending_and_old_enough():
    s = new_store("old", "recent", "p")
    s.save_result(s.get("old").id, make_metrics(), make_raw("old"), T0 - timedelta(days=31), "t")
    s.save_result(s.get("recent").id, make_metrics(), make_raw("recent"), T0 - timedelta(days=10), "t")
    assert s.next_keyword(T0, 30).keyword == "p"
    s.save_result(s.get("p").id, make_metrics(), make_raw("p"), T0, "t")
    assert s.next_keyword(T0, 30).keyword == "old"


def test_save_result_statuses():
    s = new_store("a", "b")
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    s.save_result(s.get("b").id, make_metrics(has_data=False), make_raw("b"), T0, "t")
    assert (s.get("a").status, s.get("b").status) == ("done", "no_data")


def test_three_failures_mark_failed():
    s = new_store("a")
    kid = s.get("a").id
    assert [s.record_failure(kid) for _ in range(3)] == ["pending", "pending", "failed"]
    assert s.next_keyword(T0, 30) is None


def test_recover_in_progress():
    s = new_store("a")
    s.mark_in_progress(s.get("a").id)
    assert s.recover_in_progress() == 1 and s.get("a").status == "pending"


def test_sessions_quota_and_cooldown():
    s = Store(":memory:")
    sid = s.start_session(T0)
    for _ in range(3):
        s.increment_checked(sid)
    s.end_session(sid, T0, "tanda_bahaya", T0 + timedelta(hours=24))
    assert s.checked_on(T0.date(), T0.tzinfo) == 3
    assert s.checked_on((T0 + timedelta(days=1)).date(), T0.tzinfo) == 0
    assert s.active_cooldown_until(T0 + timedelta(hours=1)) == T0 + timedelta(hours=24)
    assert s.active_cooldown_until(T0 + timedelta(hours=25)) is None
    assert s.last_session()["stop_reason"] == "tanda_bahaya"


def test_latest_results_newest_per_keyword_with_parent():
    s = new_store("a")
    s.add_related(s.get("a").id, ["b"], 10, 2, T0)
    s.save_result(s.get("b").id, make_metrics(volume=1), make_raw("b"), T0, "t")
    s.save_result(s.get("b").id, make_metrics(volume=2, related=("z",)), make_raw("b"), T0 + timedelta(days=40), "t")
    [row] = s.latest_results()
    assert (row.keyword, row.parent_keyword, row.metrics.search_volume, row.metrics.related) == ("b", "a", 2, ("z",))
    assert len(s.all_results()) == 2
