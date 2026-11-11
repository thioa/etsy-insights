from datetime import datetime, timezone

from etsy_insights.printify_store import (Blueprint, PrintifyStore, SyncedProduct, SyncedType, SyncResult)
from etsy_insights.product_words import words_for_title
from etsy_insights.store import Store

NOW = datetime(2026, 11, 11, 5, 0, tzinfo=timezone.utc)
SWEAT = "Unisex Heavy Blend™ Crewneck Sweatshirt"
MUG = "Accent Coffee Mug, 11oz"
TEE = "Unisex Jersey Short Sleeve Tee"
BLUEPRINTS = (Blueprint(6, SWEAT, "Gildan", "18000"), Blueprint(68, MUG, "Generic brand", ""),
              Blueprint(384, TEE, "Bella+Canvas", "3001"))


def own(bp, pp, title, low, high, ship=475):
    return SyncedType(bp, pp, title, "Monster Digital", "own", low, high, ship, 3, True)


def product(pid, bp, pp, title, low, high, tags=()):
    return SyncedProduct(pid, bp, pp, title, tuple(tags), low, high)


def result(types, products=(), blueprints=BLUEPRINTS):
    return SyncResult(111, "My Etsy Shop", tuple(blueprints), tuple(products), tuple(types))


def open_store(tmp_path):
    store = Store(tmp_path / "etsy.db")
    return store, PrintifyStore(store)


def by_key(ps):
    return {(t.blueprint_id, t.print_provider_id): t for t in ps.types()}


def test_schema_created_by_store(tmp_path):
    store, _ = open_store(tmp_path)
    names = {r[0] for r in store.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"printify_meta", "printify_blueprints", "printify_types", "printify_products",
            "keyword_product_links"} <= names


def test_apply_sync_creates_own_types(tmp_path):
    store, ps = open_store(tmp_path)
    ps.apply_sync(result([own(6, 99, SWEAT, 1300, 1900)],
                         [product("a", 6, 99, "Mom sweatshirt", 1350, 1600, ["mom gift"]),
                          product("b", 6, 99, "Dad sweatshirt", 1300, 1900)]), NOW)
    (t,) = ps.types()
    assert (t.source, t.cost_min_cents, t.cost_max_cents, t.shipping_us_cents, t.handling_days) == ("own", 1300, 1900, 475, 3)
    assert t.words == tuple(words_for_title(SWEAT)) and t.available and t.synced_at == NOW
    assert sorted(p.id for p in ps.products()) == ["a", "b"]
    assert ps.products()[0].tags == ("mom gift",)
    assert ps.meta("shop_id") == "111" and ps.meta("shop_title") == "My Etsy Shop" and ps.meta("last_sync_at")


def test_apply_sync_rules(tmp_path):
    store, ps = open_store(tmp_path)
    store.sync_user_keywords(["sweatshirt"], NOW)
    ps.apply_sync(result([own(6, 99, SWEAT, 1300, 1900), own(68, 1, MUG, 512, 512),
                          own(384, 29, TEE, 900, 900)]), NOW)
    keys = by_key(ps)
    ps.link(store.get("sweatshirt").id, keys[(68, 1)].id)          # mug ditautkan manual
    ps.update_type(keys[(6, 99)].id, words=["crewneck"])            # kata diedit
    picked = ps.add_picked(1000, 7, "Velveteen Plush Blanket", "Prov", 2000, 800, 4, NOW)
    gone = ps.add_picked(2000, 8, "Old Thing", "Prov", 100, 100, 2, NOW)
    # sync berikutnya: tee dan mug hilang dari toko; blanket kini dimiliki; Old Thing tidak tersedia lagi
    ps.apply_sync(result([own(6, 99, SWEAT, 1250, 1900), own(1000, 7, "Velveteen Plush Blanket", 1500, 1700),
                          SyncedType(2000, 8, "Old Thing", "Prov", "picked", None, None, None, None, False)]), NOW)
    keys = by_key(ps)
    assert (384, 29) not in keys                                     # own hilang tanpa tautan → dihapus
    assert keys[(68, 1)].source == "picked" and keys[(68, 1)].cost_min_cents == 512   # own bertaut → picked
    assert keys[(1000, 7)].source == "own" and keys[(1000, 7)].cost_min_cents == 1500  # picked → own
    assert keys[(1000, 7)].id == picked.id
    assert keys[(2000, 8)].available is False and keys[(2000, 8)].id == gone.id
    assert keys[(6, 99)].words == ("crewneck",) and keys[(6, 99)].cost_min_cents == 1250
    assert ps.links() == {"sweatshirt": keys[(68, 1)].id}


def test_edits_during_sync_are_kept(tmp_path):
    store, ps = open_store(tmp_path)
    ps.apply_sync(result([own(6, 99, SWEAT, 1300, 1900)]), NOW)
    pending = result([own(6, 99, SWEAT, 1300, 1900)])
    ps.update_type(ps.types()[0].id, words=["crewneck"])
    ps.apply_sync(pending, NOW)
    assert ps.types()[0].words == ("crewneck",)


def test_failed_sync_records_error_only(tmp_path):
    store, ps = open_store(tmp_path)
    ps.apply_sync(result([own(6, 99, SWEAT, 1300, 1900)]), NOW)
    before = ps.types()
    ps.record_sync_error("x")
    assert ps.meta("last_sync_error") == "x" and ps.types() == before
    ps.apply_sync(result([own(6, 99, SWEAT, 1300, 1900)]), NOW)
    assert ps.meta("last_sync_error") is None


def test_picked_crud_and_links(tmp_path):
    store, ps = open_store(tmp_path)
    store.sync_user_keywords(["sweatshirt"], NOW)
    ps.apply_sync(result([own(6, 99, SWEAT, 1300, 1900)]), NOW)
    own_id = ps.types()[0].id
    tee = ps.add_picked(384, 29, TEE, "Monster Digital", None, None, None, NOW)
    assert tee.source == "picked" and tee.words == tuple(words_for_title(TEE)) and tee.cost_min_cents is None
    assert ps.update_type(tee.id, cost_cents=1250).cost_min_cents == 1250
    assert ps.picked_keys() == [(384, 29)]
    kid = store.get("sweatshirt").id
    ps.link(kid, tee.id)
    assert ps.links() == {"sweatshirt": tee.id}
    assert ps.remove_picked(own_id) is False
    assert ps.remove_picked(tee.id) is True and ps.type(tee.id) is None and ps.links() == {}
    ps.link(kid, own_id)
    ps.link(kid, None)
    assert ps.links() == {}


def test_search_blueprints(tmp_path):
    store, ps = open_store(tmp_path)
    assert ps.has_blueprints() is False
    ps.apply_sync(result([]), NOW)
    assert ps.has_blueprints() is True
    assert [b.id for b in ps.search_blueprints("MUG")] == [68]
    assert [b.id for b in ps.search_blueprints("gildan")] == [6]
    assert [b.id for b in ps.search_blueprints("3001")] == [384]
    assert len(ps.search_blueprints("u", limit=2)) == 2
