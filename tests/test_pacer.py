import random
from datetime import timedelta

from etsy_insights.config import Config
from etsy_insights.pacer import Pacer, cooldown_end, remaining_quota
from tests.helpers import T0


def test_ranges_and_chances():
    p = Pacer(Config(), random.Random(1))
    typing = [p.typing_delay_ms() for _ in range(2000)]
    assert all(60 <= t <= 1080 for t in typing)
    assert 0.06 <= sum(t > 180 for t in typing) / 2000 <= 0.14
    assert all(5 <= p.dwell_seconds() <= 15 for _ in range(500))
    assert all(20 <= p.gap_seconds() <= 60 for _ in range(500))
    assert all(120 <= p.break_seconds() <= 300 for _ in range(500))
    assert {p.break_every() for _ in range(500)} == {8, 9, 10, 11, 12}
    assert 0.45 <= sum(p.should_scroll() for _ in range(2000)) / 2000 <= 0.55


def test_same_seed_same_sequence():
    a, b = Pacer(Config(), random.Random(7)), Pacer(Config(), random.Random(7))
    assert [a.gap_seconds() for _ in range(5)] == [b.gap_seconds() for _ in range(5)]


def test_remaining_quota():
    c = Config()
    assert remaining_quota(c, 30) == 20 and remaining_quota(c, 70) == 0
    assert remaining_quota(c, 0, max_keywords=3) == 3 and remaining_quota(c, 49, max_keywords=3) == 1


def test_cooldown_end():
    assert cooldown_end(T0, Config()) == T0 + timedelta(hours=24)
    assert cooldown_end(T0, Config(pendinginan_jam=36)) == T0 + timedelta(hours=36)
