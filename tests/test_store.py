from datetime import timedelta

from etsy_insights.store import Store, normalize_keyword, read_keywords_file
import sqlite3

from tests.helpers import T0, make_metrics, make_raw, make_related


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


def test_save_result_statuses():
    s = new_store("a", "b")
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    s.save_result(s.get("b").id, make_metrics(has_data=False), make_raw("b"), T0, "t")
    assert (s.get("a").status, s.get("b").status) == ("done", "no_data")


def test_three_failures_mark_failed():
    s = new_store("a")
    kid = s.get("a").id
    assert [s.record_failure(kid) for _ in range(3)] == ["pending", "pending", "failed"]
    assert s.next_user_pending() is None


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
    s.save_harvest(s.get("a").id, [make_related("b")], 200, 2, T0)
    s.save_result(s.get("b").id, make_metrics(volume=1), make_raw("b"), T0, "t")
    s.save_result(s.get("b").id, make_metrics(volume=2, related=("z",)), make_raw("b"), T0 + timedelta(days=40), "t")
    [row] = s.latest_results()
    assert (row.keyword, row.parent_keyword, row.metrics.search_volume, row.metrics.related) == ("b", "a", 2, ("z",))
    assert len(s.all_results()) == 3


def test_read_keywords_file_other_encodings(tmp_path):
    p = tmp_path / "k16.txt"
    p.write_bytes("café mug\nboho\n".encode("utf-16"))
    assert read_keywords_file(p) == ["café mug", "boho"]
    p2 = tmp_path / "kmac.txt"
    p2.write_bytes("café mug\n".encode("mac_roman"))
    assert read_keywords_file(p2) == ["café mug"]


def test_save_result_keeps_level_and_wow():
    s = new_store("a")
    s.save_result(s.get("a").id, make_metrics(level=3, wow=22.7), make_raw("a"), T0, "t")
    [row] = s.latest_results()
    assert (row.kind, row.metrics.conversion_level, row.metrics.wow_pct) == ("search", 3, 22.7)


def test_save_harvest_inserts_new_and_counts():
    s = new_store("a")
    n = s.save_harvest(s.get("a").id, [make_related("x"), make_related("y", level=4), make_related("A"),
                                       make_related(" ")], 200, 2, T0)
    assert n == 2
    x = s.get("x")
    assert (x.status, x.depth, x.parent_keyword, x.source) == ("harvested", 1, "a", "related")
    rows = {r.keyword: r for r in s.latest_results()}
    assert rows["y"].kind == "panen" and rows["y"].metrics.conversion_level == 4
    assert rows["y"].metrics.conversion_rate is None


def test_save_harvest_max_count_and_depth():
    s = new_store("a")
    assert s.save_harvest(s.get("a").id, [make_related("x"), make_related("y")], 1, 2, T0) == 1
    assert s.get("y") is None
    s.save_harvest(s.get("x").id, [make_related("x2")], 200, 2, T0)
    assert s.get("x2").depth == 2
    assert s.save_harvest(s.get("x2").id, [make_related("x3")], 200, 2, T0) == 0 and s.get("x3") is None


def test_save_harvest_updates_panen_row_without_duplicates():
    s = new_store("a", "b")
    s.save_harvest(s.get("a").id, [make_related("x", volume=1000)], 200, 2, T0)
    assert s.save_harvest(s.get("b").id, [make_related("x", volume=2000)], 200, 2, T0 + timedelta(hours=1)) == 0
    assert [r.metrics.search_volume for r in s.all_results() if r.keyword == "x"] == [2000]
    assert s.get("x").parent_keyword == "a"


def test_save_harvest_skips_searched_keywords():
    s = new_store("a", "b")
    s.save_result(s.get("a").id, make_metrics(volume=1000), make_raw("a"), T0, "t")
    s.save_harvest(s.get("b").id, [make_related("a", volume=5)], 200, 2, T0 + timedelta(hours=1))
    [row] = [r for r in s.latest_results() if r.keyword == "a"]
    assert (row.kind, row.metrics.search_volume) == ("search", 1000)


def test_queue_primitives():
    s = new_store("u1", "u2")
    s.save_harvest(s.get("u1").id, [make_related("h1"), make_related("h2")], 200, 2, T0)
    s.save_harvest(s.get("h1").id, [make_related("deep")], 200, 2, T0)
    assert s.next_user_pending().keyword == "u1"
    assert s.next_user_pending(exclude_ids={s.get("u1").id}).keyword == "u2"
    assert sorted(r.keyword for r in s.harvest_candidates(2)) == ["h1", "h2"]
    assert [r.keyword for r in s.harvest_candidates(2, exclude_ids={s.get("h1").id})] == ["h2"]
    s.save_result(s.get("u1").id, make_metrics(), make_raw("u1"), T0 - timedelta(days=31), "t")
    s.save_result(s.get("u2").id, make_metrics(), make_raw("u2"), T0 - timedelta(days=3), "t")
    assert s.next_recheck(T0, 30).keyword == "u1"
    assert s.next_recheck(T0, 30, exclude_ids={s.get("u1").id}) is None


def test_failure_and_recovery_return_to_source_queue():
    s = new_store("a")
    s.save_harvest(s.get("a").id, [make_related("x")], 200, 2, T0)
    x = s.get("x").id
    s.mark_in_progress(x)
    assert s.record_failure(x) == "harvested"
    s.mark_in_progress(x)
    s.recover_in_progress()
    assert s.get("x").status == "harvested"
    s.mark_in_progress(s.get("a").id)
    s.return_to_queue(s.get("a").id)
    assert s.get("a").status == "pending"


def test_stop_reasons_on():
    s = Store(":memory:")
    sid = s.start_session(T0)
    s.end_session(sid, T0, "kuota_etsy", None)
    assert s.stop_reasons_on(T0.date(), T0.tzinfo) == ["kuota_etsy"]
    assert s.stop_reasons_on((T0 + timedelta(days=1)).date(), T0.tzinfo) == []


def test_migrates_old_database(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE keywords (id INTEGER PRIMARY KEY, keyword TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
            parent_id INTEGER, depth INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', added_at TEXT NOT NULL,
            last_checked_at TEXT, fail_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE results (id INTEGER PRIMARY KEY, keyword_id INTEGER NOT NULL, checked_at TEXT NOT NULL,
            has_data INTEGER NOT NULL, search_volume INTEGER, conversion_rate REAL, competition_value REAL,
            competition_kind TEXT, trend_json TEXT, related_json TEXT, raw_json TEXT, parser_version TEXT);""")
    con.close()
    s = Store(db)
    s.sync_user_keywords(["a"], T0)
    s.save_result(s.get("a").id, make_metrics(level=1), make_raw("a"), T0, "t")
    assert s.latest_results()[0].metrics.conversion_level == 1


def test_sync_promotes_harvested_to_user():
    s = new_store("a")
    s.save_harvest(s.get("a").id, [make_related("b")], 200, 2, T0)
    assert s.sync_user_keywords(["b"], T0) == 1
    b = s.get("b")
    assert (b.source, b.depth, b.parent_keyword, b.status) == ("user", 0, None, "pending")
