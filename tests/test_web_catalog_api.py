import pytest

from tests.printify_fake import FakePrintify
from tests.web_helpers import TOKEN, printify_app, seeded_home

H = {"X-App-Token": TOKEN}


@pytest.fixture
def fake():
    with FakePrintify() as server:
        yield server.load_default()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return seeded_home(tmp_path / "home")


def connected(home, fake):
    _, c = printify_app(home, fake)
    assert c.post("/api/printify/token", json={"token": "secret-tok-9876"}, headers=H).status_code == 200
    assert c.post("/api/printify/sync", headers=H).status_code == 202
    return c


def requests_to(fake, path):
    return sum(1 for _, p, _, _ in fake.requests if p == path)


def test_research_api(home, fake):
    _, c = printify_app(home, fake)
    r = c.post("/api/catalog/research", json={"category": "necklace"}, headers=H)
    assert r.status_code == 200 and r.get_json()["added"] == ["necklace", "custom necklace", "personalized necklace"]
    assert "custom necklace" in (home / "keywords.txt").read_text()
    r = c.post("/api/catalog/research", json={"category": "necklace"}, headers=H)
    assert r.status_code == 409 and r.get_json()["error"] == "Already in the research queue."
    for category in ("other", "nope"):
        r = c.post("/api/catalog/research", json={"category": category}, headers=H)
        assert r.status_code == 404 and r.get_json()["error"] == "Unknown category."
    assert c.post("/api/catalog/research", json={"category": "pet bowl"}).status_code == 403


def test_shipping_api_uses_cache(home, fake):
    c = connected(home, fake)
    url, path = "/api/catalog/shipping?blueprint_id=384&provider_id=29", "/v1/catalog/blueprints/384/print_providers/29/shipping.json"
    assert c.get(url, headers=H).get_json() == {"shipping_us_cents": None, "shipping_text": "No US shipping",
                                                "handling_days": 4}
    c.get(url, headers=H)
    assert requests_to(fake, path) == 1
    assert c.get("/api/catalog/shipping?blueprint_id=6&provider_id=99", headers=H).get_json() == {
        "shipping_us_cents": 475, "shipping_text": "US$4.75", "handling_days": 3}
    assert c.get(url).status_code == 403


def test_providers_and_add_use_cache(home, fake):
    c = connected(home, fake)
    providers_path = "/v1/catalog/blueprints/384/print_providers.json"
    shipping_path = "/v1/catalog/blueprints/384/print_providers/29/shipping.json"
    for _ in range(2):
        assert c.get("/api/printify/providers?blueprint_id=384", headers=H).get_json()["providers"] == [
            {"id": 29, "title": "Monster Digital"}]
    assert requests_to(fake, providers_path) == 1
    r = c.post("/api/printify/types/add", json={"blueprint_id": 384, "print_provider_id": 29, "cost_usd": "9"}, headers=H)
    assert r.status_code == 200
    c.get("/api/catalog/shipping?blueprint_id=384&provider_id=29", headers=H)
    assert requests_to(fake, providers_path) == 1 and requests_to(fake, shipping_path) == 1


def test_failures_are_not_cached(home, fake):
    c = connected(home, fake)
    path = "/v1/catalog/blueprints/6/print_providers/99/shipping.json"
    fake.queue(path, *[(500, {}, None)] * 4)
    r = c.get("/api/catalog/shipping?blueprint_id=6&provider_id=99", headers=H)
    assert r.status_code == 400 and r.get_json()["error"].startswith("Could not reach Printify")
    r = c.get("/api/catalog/shipping?blueprint_id=6&provider_id=99", headers=H)
    assert r.status_code == 200 and r.get_json()["shipping_us_cents"] == 475


def test_malformed_shipping_is_not_cached(home, fake):
    c = connected(home, fake)
    path = "/v1/catalog/blueprints/6/print_providers/99/shipping.json"
    fake.queue(path, (200, {"unexpected": "shape"}, None))
    r = c.get("/api/catalog/shipping?blueprint_id=6&provider_id=99", headers=H)
    assert r.status_code == 400 and r.get_json()["error"].startswith("Printify sent data in an unexpected format")
    r = c.get("/api/catalog/shipping?blueprint_id=6&provider_id=99", headers=H)
    assert r.status_code == 200 and r.get_json()["shipping_us_cents"] == 475
