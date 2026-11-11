import copy
import json
from datetime import datetime, timezone

import pytest

from etsy_insights.printify_api import PrintifyClient, UnexpectedResponse
from etsy_insights.printify_store import PrintifyStore
from etsy_insights.printify_sync import (NeedShopChoice, NotConnected, SyncBusy, SyncJob, build_result, choose_shop,
                                         handling_days, us_shipping_cents)
from etsy_insights.printify_token import save_token
from etsy_insights.store import Store
from tests import printify_data as data
from tests.printify_fake import FakePrintify

NOW = datetime(2026, 11, 11, 5, 0, tzinfo=timezone.utc)
TOKEN = "secret-tok-9876"


@pytest.fixture
def fake():
    with FakePrintify() as server:
        yield server.load_default()


def client_for(fake):
    return lambda token: PrintifyClient(token, base_url=fake.url, min_interval=0, sleep=lambda s: None,
                                        no_proxy=True)


def job(tmp_path, fake, spawn=lambda f: f()):
    save_token(tmp_path, TOKEN)
    return SyncJob(tmp_path, client_for(fake), now=lambda: NOW, spawn=spawn)


def printify_store(tmp_path):
    store = Store(tmp_path / "data" / "etsy.db")
    return store, PrintifyStore(store)


def test_choose_shop():
    etsy, other = data.SHOPS
    assert choose_shop(data.SHOPS, None) == etsy
    assert choose_shop(data.SHOPS, 222) == other
    two = [etsy, {"id": 333, "title": "Second", "sales_channel": "etsy"}]
    with pytest.raises(NeedShopChoice) as err:
        choose_shop(two, None)
    assert [s["id"] for s in err.value.shops] == [111, 333]
    assert err.value.message == "Choose the Printify shop that is connected to your Etsy shop."
    with pytest.raises(NeedShopChoice):
        choose_shop([other], None)


def test_us_shipping_rules():
    assert us_shipping_cents(data.SHIPPING[(6, 99)], 1) == 475
    assert us_shipping_cents(data.SHIPPING[(68, 1)], 10) == 699
    assert us_shipping_cents(data.SHIPPING[(384, 29)], 20) is None
    euro = {"profiles": [data.profile([1], 475, ["US"], currency="EUR")]}
    assert us_shipping_cents(euro, 1) is None
    two = {"profiles": [data.profile([1], 600, ["US"]), data.profile([2], 450, ["US", "CA"])]}
    assert us_shipping_cents(two, None) == 450
    assert handling_days(data.SHIPPING[(6, 99)]) == 3


def test_build_result_from_fixtures(fake):
    steps = []
    client = client_for(fake)("tok")
    result = build_result(client, data.SHOPS[0], [(384, 29), (999, 5)], lambda s, d, t: steps.append((s, d, t)))
    types = {(t.blueprint_id, t.print_provider_id): t for t in result.types}
    sweat, mug, tee, gone = types[(6, 99)], types[(68, 1)], types[(384, 29)], types[(999, 5)]
    assert (sweat.source, sweat.cost_min_cents, sweat.cost_max_cents, sweat.shipping_us_cents, sweat.handling_days,
            sweat.provider_title, sweat.title) == ("own", 1350, 1600, 475, 3, "Monster Digital",
                                                   "Unisex Heavy Blend™ Crewneck Sweatshirt")
    assert (mug.source, mug.cost_min_cents, mug.cost_max_cents, mug.shipping_us_cents) == ("own", 512, 512, 699)
    assert (tee.source, tee.available, tee.shipping_us_cents, tee.cost_min_cents) == ("picked", True, None, None)
    assert (gone.source, gone.available) == ("picked", False)
    assert sorted(p.id for p in result.products) == ["p-mug", "p-sweat"]
    assert len(result.blueprints) == 3 and (result.shop_id, result.shop_title) == (111, "My Etsy Shop")
    assert not any("/999/" in path for _, path, _, _ in fake.requests)
    done = [d for _, d, _ in steps]
    assert done == sorted(done) and steps[-1][1] == steps[-1][2] == 3


def test_tolerant_fields(fake):
    page = copy.deepcopy(data.PRODUCTS_PAGE_1)
    page["data"][0]["tags"] = None
    for v in page["data"][0]["variants"]:
        v.pop("is_enabled")
    fake.set("/v1/shops/111/products.json?page=1", page)
    result = build_result(client_for(fake)("tok"), data.SHOPS[0], [], lambda *a: None)
    sweat = next(p for p in result.products if p.id == "p-sweat")
    assert sweat.tags == () and sweat.cost_min_cents == 900


def test_unexpected_shape_stops(fake):
    page = copy.deepcopy(data.PRODUCTS_PAGE_1)
    del page["data"][0]["variants"]
    fake.set("/v1/shops/111/products.json?page=1", page)
    with pytest.raises(UnexpectedResponse):
        build_result(client_for(fake)("tok"), data.SHOPS[0], [], lambda *a: None)


def test_job_success(tmp_path, fake):
    j = job(tmp_path, fake)
    j.start()
    status = j.status()
    assert status["state"] == "done" and status["error"] is None and status["last_sync_at"]
    store, ps = printify_store(tmp_path)
    assert sorted(t.source for t in ps.types()) == ["own", "own"]
    store.close()


def test_job_errors_keep_old_data(tmp_path, fake):
    j = job(tmp_path, fake)
    j.start()
    fake.set("/v1/shops.json", {"error": "Unauthenticated"}, status=401)
    j.start()
    status = j.status()
    message = "Printify rejected the token. Create a new token in Printify and paste it here."
    assert status["state"] == "error" and status["error"] == message
    store, ps = printify_store(tmp_path)
    assert ps.meta("last_sync_error") == message and len(ps.types()) == 2
    store.close()


def test_job_unexpected_records_without_token(tmp_path, fake):
    fake.set("/v1/catalog/blueprints.json", "oops")
    j = job(tmp_path, fake)
    j.start()
    status = j.status()
    (recording,) = (tmp_path / "rekaman").glob("printify-*.json")
    saved = json.loads(recording.read_text())
    assert saved["path"] == "/v1/catalog/blueprints.json" and saved["body"] == "oops"
    assert TOKEN not in recording.read_text()
    assert status["state"] == "error" and status["error"] == (
        "Printify sent data in an unexpected format. Sync stopped and nothing was changed. "
        f"Send this file to Claude: {recording}")


def test_job_choose_shop(tmp_path, fake):
    fake.set("/v1/shops.json", [data.SHOPS[0], {"id": 333, "title": "Second", "sales_channel": "etsy"}])
    j = job(tmp_path, fake)
    j.start()
    status = j.status()
    assert status["state"] == "choose_shop"
    assert status["shops"] == [{"id": 111, "title": "My Etsy Shop", "sales_channel": "etsy"},
                               {"id": 333, "title": "Second", "sales_channel": "etsy"}]
    store, ps = printify_store(tmp_path)
    ps.set_meta("shop_id", "111")
    store.close()
    j.start()
    assert j.status()["state"] == "done"


def test_job_busy_and_not_connected(tmp_path, fake):
    with pytest.raises(NotConnected) as err:
        SyncJob(tmp_path, client_for(fake), now=lambda: NOW).start()
    assert err.value.message == "Connect Printify first."
    j = job(tmp_path, fake, spawn=lambda f: None)
    j.start()
    assert j.status()["state"] == "running"
    with pytest.raises(SyncBusy) as err:
        j.start()
    assert err.value.message == "A sync is already running."


def test_disabled_variants_need_no_cost(fake):
    page = copy.deepcopy(data.PRODUCTS_PAGE_1)
    variants = page["data"][0]["variants"]
    variants[2]["cost"] = None                      # varian tidak aktif tanpa biaya
    variants[1]["is_enabled"] = None                # null = tetap aktif
    fake.set("/v1/shops/111/products.json?page=1", page)
    result = build_result(client_for(fake)("tok"), data.SHOPS[0], [], lambda *a: None)
    sweat = next(p for p in result.products if p.id == "p-sweat")
    assert (sweat.cost_min_cents, sweat.cost_max_cents) == (1350, 1600)


def test_image_url_from():
    from etsy_insights.printify_sync import image_url_from
    assert image_url_from(["http://x/a.png", "https://x/b.png"]) == "https://x/b.png"
    for value in (None, [], [1, "javascript:x"], "https://x/c.png"):
        assert image_url_from(value) == ""


def test_build_result_keeps_images(fake):
    blueprints = copy.deepcopy(data.BLUEPRINTS)
    blueprints[0]["images"] = ["https://images.printify.com/sweat.png"]
    fake.set("/v1/catalog/blueprints.json", blueprints)
    result = build_result(client_for(fake)("tok"), data.SHOPS[0], [], lambda *a: None)
    by_id = {b.id: b for b in result.blueprints}
    assert by_id[6].image_url == "https://images.printify.com/sweat.png" and by_id[68].image_url == ""
