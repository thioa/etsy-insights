from etsy_insights.keywords import add_keywords, list_user_keywords, prioritize, remove_keyword
from etsy_insights.store import Store
from tests.helpers import T0, make_metrics, make_raw, make_related


def home_with(tmp_path, text):
    (tmp_path / "keywords.txt").write_text(text, encoding="utf-8")
    return tmp_path


def test_add_dedupes_and_appends(tmp_path):
    home = home_with(tmp_path, "# my list\nMug")
    s = Store(":memory:")
    assert add_keywords(home, s, "mug\n\n Tote Bag \n# note\ntote bag\n", T0) == ["tote bag"]
    assert (home / "keywords.txt").read_text(encoding="utf-8") == "# my list\nMug\ntote bag\n"
    assert s.get("tote bag").status == "pending"


def test_remove_keeps_comments_and_other_lines(tmp_path):
    home = home_with(tmp_path, "# my list\nMug\n\nTote Bag\n")
    s = Store(":memory:")
    s.sync_user_keywords(["mug", "tote bag"], T0)
    assert remove_keyword(home, s, "tote bag")
    assert (home / "keywords.txt").read_text(encoding="utf-8") == "# my list\nMug\n\n"
    assert s.get("tote bag") is None


def test_remove_refuses_searched_and_restores_harvested(tmp_path):
    home = home_with(tmp_path, "a\n")
    s = Store(":memory:")
    s.sync_user_keywords(["a"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    assert not remove_keyword(home, s, "a")
    s.save_harvest(s.get("a").id, [make_related("x")], 200, 2, T0)
    assert prioritize(home, s, "x", T0) and s.get("x").source == "user"
    assert remove_keyword(home, s, "x")
    x = s.get("x")
    assert (x.source, x.depth, x.status) == ("related", 1, "harvested")


def test_prioritize_unknown_is_false_and_list_statuses(tmp_path):
    home = home_with(tmp_path, "a\nb\n")
    s = Store(":memory:")
    s.sync_user_keywords(["a", "b"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    assert not prioritize(home, s, "nope", T0)
    assert [(k.keyword, k.status) for k in list_user_keywords(home, s)] == [("a", "done"), ("b", "pending")]
