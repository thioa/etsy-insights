from datetime import timedelta

from etsy_insights.config import Config
from etsy_insights.planner import select_next, upcoming
from etsy_insights.store import Store
from tests.helpers import T0, make_metrics, make_raw, make_related


def searched_store():
    s = Store(":memory:")
    s.sync_user_keywords(["a"], T0)
    s.save_result(s.get("a").id, make_metrics(volume=1000, level=2, comp=100), make_raw("a"), T0, "t")
    s.save_harvest(s.get("a").id, [make_related("x", 5000, 50, 4), make_related("y", 200, 900000, 0),
                                   make_related("z", 50, 10, 4)], 200, 2, T0)
    return s


def test_select_next_prefers_user_pending():
    s = searched_store()
    s.sync_user_keywords(["b"], T0)
    assert select_next(s, Config(), T0).keyword == "b"


def test_select_next_picks_best_eligible_harvested():
    s = searched_store()
    assert select_next(s, Config(), T0).keyword == "x"
    assert select_next(s, Config(), T0, {s.get("x").id}).keyword == "y"
    assert select_next(s, Config(), T0, {s.get("x").id, s.get("y").id}) is None  # z tidak layak (volume < 100)


def test_select_next_falls_back_to_recheck():
    s = Store(":memory:")
    s.sync_user_keywords(["a"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0 - timedelta(days=31), "t")
    assert select_next(s, Config(), T0).keyword == "a"


def test_upcoming_lists_user_then_ranked_harvested():
    s = searched_store()
    s.sync_user_keywords(["b", "c"], T0)
    assert [q.keyword for q in upcoming(s, Config())] == ["b", "c", "x", "y"]
    assert [q.keyword for q in upcoming(s, Config(), limit=3)] == ["b", "c", "x"]


def test_select_next_scales_with_many_harvested_rows():
    import time
    s = Store(":memory:")
    users = [f"u{i}" for i in range(40)]
    s.sync_user_keywords(users, T0)
    for i, user in enumerate(users):
        s.save_result(s.get(user).id, make_metrics(), make_raw(user), T0, "t")
        s.save_harvest(s.get(user).id, [make_related(f"k{i}-{j}", 100 + j, 1000 + j, j % 5) for j in range(200)],
                       200, 2, T0)
    started = time.perf_counter()
    assert select_next(s, Config(), T0) is not None
    assert time.perf_counter() - started < 1.0
