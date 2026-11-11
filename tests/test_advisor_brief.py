import json
import time
from datetime import datetime, timezone

from etsy_insights.advisor_brief import build_inputs, select_keywords, trend_pct
from etsy_insights.advisor_key import save_key
from etsy_insights.config import Config
from etsy_insights.printify_token import save_token
from etsy_insights.score import score_all
from etsy_insights.store import Store
from etsy_insights.taste import build_profiles
from tests.helpers import make_row
from tests.web_helpers import seed_printify, seed_ready_keyword, seeded_home

NOW = datetime.now().astimezone()


def _home(tmp_path):
    home = seeded_home(tmp_path / "home")
    seed_printify(home, mug_cost=100, mug_shipping=0)
    seed_ready_keyword(home)
    return home


def _inputs(home, cfg=None):
    store = Store(home / "data" / "etsy.db")
    try:
        return build_inputs(store, cfg or Config(), NOW)
    finally:
        store.close()


def test_trend_pct():
    assert trend_pct([10] * 7 + [20] * 7) == 100.0
    assert trend_pct([10] * 10 + [5] * 7) == -50.0
    assert trend_pct([10] * 13) is None
    assert trend_pct([0] * 7 + [5] * 7) is None


def test_select_keywords_order_and_caps():
    rising = [make_row(f"rising {i}", 500, 2, 100, trend=[10] * 10 + [11 + i] * 7) for i in range(70)]
    plain = [make_row(f"plain {i}", 1000 + i, 2, 100) for i in range(300)]
    small = [make_row("small rising", 50, 2, 100, trend=[10] * 10 + [90] * 7)]
    scored = score_all(rising + plain + small, Config())
    chosen = select_keywords(scored, Config())
    names = [s.row.keyword for s in chosen]
    assert len(chosen) == 200 and len(set(names)) == 200
    assert names[:60] == [f"rising {i}" for i in range(69, 9, -1)]
    assert "small rising" not in names[:60]


def test_inputs_for_fixture_data(tmp_path):
    trend_input, analysis = _inputs(_home(tmp_path))
    assert trend_input.today == NOW.date()
    assert "Mugs" in trend_input.categories and "Other" not in trend_input.categories
    assert 0 < len(trend_input.top_keywords) <= 20
    payload = analysis.payload
    assert payload["context"]["daily_searches"] == 15
    assert payload["context"]["market"] == "Etsy buyers in the United States; free shipping"
    mug = next(c for c in payload["categories"] if c["key"] == "mug")
    assert mug["production_cost_usd"] == "1.00–1.00" and mug["in_my_products"] is True and mug["name"] == "Mugs"
    custom_mug = next(k for k in payload["keywords"] if k["keyword"] == "custom mug")
    assert custom_mug["category"] == "mug" and custom_mug["ready_to_sell"] is True
    assert custom_mug["buyers"]["paid_price"] == "US$15.30–US$18.70"
    assert "other" not in analysis.category_keys and "mug" in analysis.category_keys
    assert analysis.keyword_count == len(payload["keywords"])
    assert analysis.category_count == len(payload["categories"]) == len(analysis.category_keys)


def test_existing_keywords_exclude_harvested(tmp_path):
    home = _home(tmp_path)
    store = Store(home / "data" / "etsy.db")
    store.sync_user_keywords(["personalized", "sweatshirt", "custom", "swearshirt", "custom mug", "new idea mug"],
                             NOW)
    harvested = next(k for k, s in store.keyword_statuses().items() if s == "harvested")
    store.close()
    existing = _inputs(home)[1].payload["existing_keywords"]
    assert "new idea mug" in existing and "sweatshirt" in existing
    assert harvested not in existing


def test_brief_has_no_private_data(tmp_path):
    home = _home(tmp_path)
    save_token(home, "secret-printify-token-1")
    key = "sk-ant-api03-" + "z" * 20
    save_key(home, key)
    trend_input, analysis = _inputs(home)
    text = json.dumps(analysis.payload, ensure_ascii=False) + repr(trend_input)
    store = Store(home / "data" / "etsy.db")
    shops = {card.shop for profile in build_profiles(store).values() for card in profile.examples}
    store.close()
    assert shops
    assert "secret-printify-token-1" not in text and key not in text and "etsy.com/listing" not in text
    assert not [shop for shop in shops if shop in text]


def test_brief_caps_large_database(tmp_path):
    home = _home(tmp_path)
    store = Store(home / "data" / "etsy.db")
    db = store.connection
    stamp = datetime.now(timezone.utc).isoformat()
    db.execute("BEGIN")
    for status, count, prefix in (("harvested", 30_000, "harvest"), ("done", 5_000, "searched")):
        db.executemany("INSERT INTO keywords (keyword, source, depth, status, added_at) VALUES (?, ?, ?, ?, ?)",
                       [(f"{prefix} mug {i}", "user" if status == "done" else "panen", 1, status, stamp)
                        for i in range(count)])
    db.execute(
        "INSERT INTO results (keyword_id, checked_at, has_data, search_volume, competition_value, competition_kind, "
        "trend_json, related_json, kind, conversion_level) SELECT id, ?, 1, 100 + (id % 5000), id % 900, 'count', "
        "'[]', '[]', 'panen', id % 5 FROM keywords WHERE keyword LIKE 'harvest mug %' OR keyword LIKE 'searched mug %'",
        (stamp,))
    db.execute("COMMIT")
    store.close()
    started = time.perf_counter()
    _, analysis = _inputs(home)
    elapsed = time.perf_counter() - started
    assert len(analysis.payload["keywords"]) <= 200
    assert len(analysis.payload["existing_keywords"]) == 3000
    assert elapsed < 2, elapsed
