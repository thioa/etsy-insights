import pytest

from etsy_insights.config import Config
from etsy_insights.score import label_for, percentile_ranks, score_all
from tests.helpers import make_row


def test_percentile_ranks():
    assert percentile_ranks([10, 20, 20, 30]) == [0, 50, 50, 100]
    assert percentile_ranks([5]) == [50.0] and percentile_ranks([]) == []


def test_score_example_from_spec():
    rows = [make_row("a", 1000, 3, 100), make_row("b", 500, 2, 1000),
            make_row("c", 2000, 1, 5000), make_row("d", 50, 4, 1)]
    out = score_all(rows, Config())
    assert [s.row.keyword for s in out] == ["a", "c", "b", "d"]
    a, c, b, d = out
    assert a.score == pytest.approx(80) and c.score == pytest.approx(40) and b.score == pytest.approx(30)
    assert (a.label, c.label, b.label, d.label) == ("Potensial", "Lewati", "Lewati", "Data kurang")
    assert a.searches_per_listing == pytest.approx(10.0) and d.score is None and not d.eligible


def test_emas_when_top_third_everywhere():
    rows = [make_row("a", 1000, 3, 100), make_row("b", 500, 2, 1000),
            make_row("c", 2000, 1, 5000), make_row("e", 4000, 4, 10)]
    e = score_all(rows, Config())[0]
    assert e.row.keyword == "e" and e.label == "Emas" and e.score == pytest.approx(100)


def test_label_boundaries():
    assert label_for(200 / 3, 200 / 3, 200 / 3, 66.7) == "Emas"
    assert label_for(66.6, 100, 100, 90) == "Potensial"
    assert label_for(10, 10, 10, 60) == "Potensial" and label_for(10, 10, 10, 59.99) == "Lewati"


def test_competition_levels():
    rows = [make_row("x", 1000, 2, 1, kind="level"), make_row("y", 1000, 2, 2, kind="level"),
            make_row("z", 1000, 2, 3, kind="level")]
    by = {s.row.keyword: s for s in score_all(rows, Config())}
    assert (by["x"].p_low_competition, by["y"].p_low_competition, by["z"].p_low_competition) == (100, 50, 0)
    assert by["x"].searches_per_listing is None


def test_missing_metric_reweights():
    rows = [make_row("p", 1000, None, 10), make_row("q", 2000, None, 20)]
    by = {s.row.keyword: s for s in score_all(rows, Config())}
    assert by["p"].eligible and by["p"].p_conversion is None
    assert by["p"].score == pytest.approx(0.25 / 0.65 * 100) and by["q"].score == pytest.approx(0.40 / 0.65 * 100)


def test_no_data_rows_are_data_kurang():
    [s] = score_all([make_row("n", None, None, None, has_data=False)], Config())
    assert s.label == "Data kurang" and not s.eligible


def test_conversion_uses_level_not_rate():
    rows = [make_row("hi", 1000, 4, 100, rate=0.0001), make_row("lo", 1000, 0, 100, rate=0.9)]
    by = {s.row.keyword: s for s in score_all(rows, Config())}
    assert by["hi"].p_conversion == 100 and by["lo"].p_conversion == 0
