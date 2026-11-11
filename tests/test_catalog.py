from datetime import datetime

from etsy_insights.catalog import (ResearchState, categories_from, research, research_seeds, research_state,
                                   sort_summaries, summarize, top_keywords)
from etsy_insights.config import Config
from etsy_insights.models import RelatedKeyword
from etsy_insights.printify_store import Blueprint, PrintifyStore
from etsy_insights.product_words import ENTRIES, matches
from etsy_insights.store import Store
from tests.web_helpers import seed_printify, seed_ready_keyword, seeded_home


def bp(blueprint_id, title, image=""):
    return Blueprint(blueprint_id, title, "Brand", "M", image)


def fixture_summaries(tmp_path):
    home = seeded_home(tmp_path)
    seed_ready_keyword(home)
    seed_printify(home, mug_cost=100, mug_shipping=0)
    store = Store(home / "data" / "etsy.db")
    categories = categories_from(PrintifyStore(store).blueprints())
    return home, store, summarize(store, Config(), categories)


def test_categories_from_groups_by_head_noun():
    cats = categories_from([bp(6, "Unisex Heavy Blend™ Crewneck Sweatshirt"), bp(7, "Unisex Heavy Blend™ Hooded Sweatshirt"),
                            bp(68, "Accent Coffee Mug, 11oz"), bp(69, "Ceramic Mug 15oz"), bp(2000, "Something Unusual")])
    assert set(cats) == {"sweatshirt", "hoodie", "mug", "other"}
    assert (cats["mug"].name, len(cats["mug"].blueprints), cats["mug"].slug) == ("Mugs", 2, "mug")


def test_category_photo_skips_missing():
    cats = categories_from([bp(68, "Accent Coffee Mug", ""), bp(69, "Ceramic Mug", "https://x/b.png")])
    assert cats["mug"].photo == "https://x/b.png"
    assert categories_from([bp(68, "Accent Coffee Mug")])["mug"].photo == ""


def test_research_state_and_harvested_seeds(tmp_path):
    seeds = research_seeds("necklace")
    assert seeds == ["necklace", "custom necklace", "personalized necklace"]
    assert research_state({}, "necklace") == ResearchState("available", 0)
    mixed = {"necklace": "harvested", "custom necklace": "done", "personalized necklace": "done"}
    assert research_state(mixed, "necklace").status == "available"
    assert research_state({k: "pending" for k in seeds}, "necklace") == ResearchState("in_queue", 3)
    partly = {"necklace": "done", "custom necklace": "no_data", "personalized necklace": "in_progress"}
    assert research_state(partly, "necklace") == ResearchState("in_queue", 1)
    assert research_state({k: "done" for k in seeds}, "necklace") == ResearchState("researched", 0)
    assert research_state({}, "other").status == "none"

    home = seeded_home(tmp_path)
    store = Store(home / "data" / "etsy.db")
    now = datetime.now().astimezone()
    store.save_harvest(store.get("sweatshirt").id, [RelatedKeyword("necklace", 1000, 100, 2)], 200, 2, now)
    store.sync_user_keywords(["custom necklace"], now)
    store.connection.execute("UPDATE keywords SET status = 'done' WHERE keyword = 'custom necklace'")
    assert store.get("necklace").status == "harvested"
    assert research(home, store, "necklace", now) == ["necklace", "personalized necklace"]
    assert store.get("necklace").status == "pending" and store.get("personalized necklace").status == "pending"
    assert "personalized necklace" in (home / "keywords.txt").read_text()


def test_summary_for_fixture_data(tmp_path):
    home, store, sums = fixture_summaries(tmp_path)
    sweat = sums["sweatshirt"]
    assert sweat.status == "researched" and sweat.searched >= 1 and sweat.ready == 0 and sweat.in_my_products
    rows = [r for r in store.latest_results() if matches(r.keyword, ENTRIES["sweatshirt"])]
    top = max(rows, key=lambda r: r.metrics.search_volume or 0)
    assert sweat.most_searched == (top.keyword, top.metrics.search_volume) and sweat.keywords == len(rows)
    assert sums["mug"].ready == 1 and sums["mug"].in_my_products
    bowl = sums["pet bowl"]
    assert (bowl.status, bowl.most_searched, bowl.ready, bowl.keywords, bowl.models) == ("not_researched", None, None, 0, 1)
    assert bowl.research.status == "available" and not bowl.in_my_products
    neck = sums["necklace"]  # fixture: hanya keyword hasil panen (custom name necklace, personalized necklace, …)
    assert neck.status == "harvested_only" and neck.searched == 0 and neck.research.status == "available"
    assert sums["t shirt"].status == "harvested_only"
    assert sums["other"].research.status == "none"


def test_sort_orders(tmp_path):
    home, store, sums = fixture_summaries(tmp_path)
    rest = [s for s in sums.values() if s.info.main != "other"]
    expected = sorted(rest, key=lambda s: (-(s.gold + s.potential), -(s.best[1] if s.best else -1),
                                           s.keywords == 0, s.info.name))
    assert [s.info.main for s in sort_summaries(sums.values(), "best")] == [s.info.main for s in expected] + ["other"]
    names = [s.info.name for s in sort_summaries(sums.values(), "name")]
    assert names[:-1] == sorted(names[:-1]) and names[-1] == "Other"
    volumes = [s.most_searched[1] if s.most_searched else -1 for s in sort_summaries(sums.values(), "searched")][:-1]
    assert volumes == sorted(volumes, reverse=True)
    models = [s.models for s in sort_summaries(sums.values(), "products")][:-1]
    assert models == sorted(models, reverse=True)


def test_top_keywords(tmp_path):
    home, store, sums = fixture_summaries(tmp_path)
    top = top_keywords(store, Config(), "sweatshirt", limit=3)
    assert 0 < len(top) <= 3 and [s.score for s in top] == sorted((s.score for s in top), reverse=True)
    assert all(matches(s.row.keyword, ENTRIES["sweatshirt"]) for s in top)


def test_summaries_are_reused_until_data_changes(tmp_path, monkeypatch):
    import etsy_insights.catalog as catalog
    home, store, first = fixture_summaries(tmp_path)
    categories = categories_from(PrintifyStore(store).blueprints())
    calls = []
    real = catalog.score_all
    monkeypatch.setattr(catalog, "score_all", lambda rows, cfg: calls.append(1) or real(rows, cfg))
    assert catalog.summarize(store, Config(), categories) == first
    assert calls == []                                       # dari cache
    research(home, store, "pet bowl", datetime.now().astimezone())
    after = catalog.summarize(store, Config(), categories)   # data berubah → dihitung ulang
    assert len(calls) == 1 and after["pet bowl"].research.status == "in_queue"
    PrintifyStore(store).update_type(PrintifyStore(store).types()[0].id, words=["mug"])
    catalog.summarize(store, Config(), categories)           # data Printify berubah → dihitung ulang
    assert len(calls) == 2
