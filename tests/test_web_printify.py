import logging
from types import SimpleNamespace

import pytest

from etsy_insights.printify_store import PrintifyStore
from etsy_insights.store import Store
from tests import printify_data as data
from tests.printify_fake import FakePrintify
from tests.web_helpers import TOKEN, printify_app, seeded_home

H = {"X-App-Token": TOKEN}
SECRET = "secret-tok-9876"
POSTS = ["/api/printify/token", "/api/printify/test", "/api/printify/disconnect", "/api/printify/shop",
         "/api/printify/sync", "/api/printify/types/add", "/api/printify/types/update", "/api/printify/types/remove",
         "/api/printify/link", "/api/printify/suggestions/add"]


@pytest.fixture
def fake():
    with FakePrintify() as server:
        yield server.load_default()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return seeded_home(tmp_path / "home")


def connect(c):
    r = c.post("/api/printify/token", json={"token": SECRET}, headers=H)
    assert r.status_code == 200, r.get_json()
    return r


def synced(home, fake):
    app, c = printify_app(home, fake)
    connect(c)
    assert c.post("/api/printify/sync", headers=H).status_code == 202
    assert c.get("/api/printify/status").get_json()["state"] == "done"
    return app, c


def types_by_key(home):
    store = Store(home / "data" / "etsy.db")
    try:
        return {(t.blueprint_id, t.print_provider_id): t for t in PrintifyStore(store).types()}
    finally:
        store.close()


def test_page_not_connected(home, fake):
    _, c = printify_app(home, fake)
    html = c.get("/printify").get_data(as_text=True)
    for text in ("Connect Printify", "Paste your Printify token", "shops.read", "products.read", "catalog.read",
                 'href="/printify"'):
        assert text in html


def test_token_saved_after_test(home, fake):
    _, c = printify_app(home, fake)
    body = connect(c).get_json()
    assert [s["id"] for s in body["shops"]] == [111, 222] and SECRET not in str(body)
    assert (home / "printify-token").exists()
    html = c.get("/printify").get_data(as_text=True)
    assert "token ends …9876" in html and "Never synced" in html


def test_bad_token_not_saved(home, fake):
    fake.set("/v1/shops.json", {"error": "Unauthenticated"}, status=401)
    _, c = printify_app(home, fake)
    r = c.post("/api/printify/token", json={"token": SECRET}, headers=H)
    assert r.status_code == 400
    assert r.get_json()["error"] == "Printify rejected the token. Create a new token in Printify and paste it here."
    assert not (home / "printify-token").exists()


def test_sync_and_types_table(home, fake):
    _, c = synced(home, fake)
    html = c.get("/printify").get_data(as_text=True)
    for text in ("Your product", "US$13.50", "US$4.75", "Monster Digital", "Matches", "Shop: My Etsy Shop",
                 "Last sync:"):
        assert text in html


def test_sync_conflicts(home, fake):
    _, c = printify_app(home, fake, spawn=lambda f: None)
    r = c.post("/api/printify/sync", headers=H)
    assert r.status_code == 409 and r.get_json()["error"] == "Connect Printify first."
    connect(c)
    assert c.post("/api/printify/sync", headers=H).status_code == 202
    r = c.post("/api/printify/sync", headers=H)
    assert r.status_code == 409 and r.get_json()["error"] == "A sync is already running."


def test_choose_shop_flow(home, fake):
    fake.set("/v1/shops.json", [data.SHOPS[0], {"id": 333, "title": "Second", "sales_channel": "etsy"}])
    _, c = printify_app(home, fake)
    connect(c)
    c.post("/api/printify/sync", headers=H)
    html = c.get("/printify").get_data(as_text=True)
    assert "Use this shop" in html and "Second" in html
    assert c.post("/api/printify/shop", json={"shop_id": 111}, headers=H).status_code == 200
    c.post("/api/printify/sync", headers=H)
    assert c.get("/api/printify/status").get_json()["state"] == "done"


def test_catalog_and_providers(home, fake):
    _, c = printify_app(home, fake)
    connect(c)
    r = c.get("/api/printify/catalog?q=mug")
    assert r.status_code == 409 and r.get_json()["error"] == "Run Sync once to search the catalog."
    c.post("/api/printify/sync", headers=H)
    assert [b["id"] for b in c.get("/api/printify/catalog?q=mug").get_json()["results"]] == [68]
    assert c.get("/api/printify/providers?blueprint_id=6").get_json()["providers"] == [{"id": 99, "title": "Monster Digital"}]


def test_picked_types_api(home, fake):
    _, c = synced(home, fake)
    r = c.post("/api/printify/types/add", json={"blueprint_id": 384, "print_provider_id": 29, "cost_usd": "0"}, headers=H)
    assert r.status_code == 400 and r.get_json()["error"] == "Enter an amount from 0.01 to 500."
    r = c.post("/api/printify/types/add", json={"blueprint_id": 384, "print_provider_id": 29, "cost_usd": "12.50"}, headers=H)
    assert r.status_code == 200
    tee = types_by_key(home)[(384, 29)]
    assert (tee.source, tee.cost_min_cents, tee.shipping_us_cents, tee.provider_title) == ("picked", 1250, None, "Monster Digital")
    r = c.post("/api/printify/types/update", json={"type_id": str(tee.id), "words": "tee, t shirt"}, headers=H)
    assert r.status_code == 200
    tee = types_by_key(home)[(384, 29)]
    assert tee.words == ("tee", "t shirt") and tee.words_edited
    own = types_by_key(home)[(6, 99)]
    r = c.post("/api/printify/types/update", json={"type_id": own.id, "cost_usd": "9"}, headers=H)
    assert r.status_code == 400 and r.get_json()["error"] == "Cost can only be set for picked product types."
    assert c.post("/api/printify/types/remove", json={"type_id": own.id}, headers=H).status_code == 400
    assert c.post("/api/printify/types/remove", json={"type_id": tee.id}, headers=H).status_code == 200
    assert (384, 29) not in types_by_key(home)


def test_link_api(home, fake):
    _, c = synced(home, fake)
    mug = types_by_key(home)[(68, 1)]
    assert c.post("/api/printify/link", json={"keyword": "Sweatshirt", "type_id": mug.id}, headers=H).status_code == 200
    store = Store(home / "data" / "etsy.db")
    assert PrintifyStore(store).links() == {"sweatshirt": mug.id}
    store.close()
    assert c.post("/api/printify/link", json={"keyword": "sweatshirt", "type_id": None}, headers=H).status_code == 200
    store = Store(home / "data" / "etsy.db")
    assert PrintifyStore(store).links() == {}
    store.close()
    assert c.post("/api/printify/link", json={"keyword": "never seen", "type_id": mug.id}, headers=H).status_code == 404


def test_suggestions_add(home, fake):
    _, c = synced(home, fake)
    assert "mom gift" in c.get("/printify").get_data(as_text=True)
    r = c.post("/api/printify/suggestions/add", json={"keywords": ["mom gift"]}, headers=H)
    assert r.status_code == 200
    assert "mom gift" in (home / "keywords.txt").read_text()
    assert 'value="mom gift"' not in c.get("/printify").get_data(as_text=True)


def test_token_never_leaks(home, fake, caplog):
    caplog.set_level(logging.DEBUG)
    _, c = synced(home, fake)
    for path in ("/", "/printify", "/opportunities", "/settings", "/api/status", "/api/printify/status"):
        assert SECRET not in c.get(path).get_data(as_text=True), path
    assert SECRET.encode() not in c.get("/download/excel").get_data()
    assert SECRET not in caplog.text


def test_new_posts_need_app_token(home, fake):
    _, c = printify_app(home, fake)
    for path in POSTS:
        assert c.post(path, json={}).status_code == 403, path


def test_page_states(home, fake):
    app, c = synced(home, fake)
    store = Store(home / "data" / "etsy.db")
    ps = PrintifyStore(store)
    ps.update_type(types_by_key(home)[(68, 1)].id, words=[])
    ps.add_picked(999, 5, "Retired Thing", "Prov", 100, 100, 2, ps.types()[0].synced_at)
    store.close()
    c.post("/api/printify/sync", headers=H)
    html = c.get("/printify").get_data(as_text=True)
    assert "Add product words" in html and "No longer available" in html
    fake.set("/v1/shops.json", {"error": "Unauthenticated"}, status=401)
    c.post("/api/printify/sync", headers=H)
    assert "Printify rejected the token." in c.get("/printify").get_data(as_text=True)
    app.extensions["etsy"].printify_job = SimpleNamespace(status=lambda: {
        "state": "running", "step": "Reading your products", "done": 1, "total": 4, "error": None, "shops": [],
        "last_sync_at": None})
    assert "Syncing… Reading your products (1 of 4)" in c.get("/printify").get_data(as_text=True)


def test_disconnect_keeps_data(home, fake):
    _, c = synced(home, fake)
    assert c.post("/api/printify/disconnect", headers=H).status_code == 200
    assert not (home / "printify-token").exists()
    html = c.get("/printify").get_data(as_text=True)
    assert "Connect Printify" in html and "Monster Digital" in html
