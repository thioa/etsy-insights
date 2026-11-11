"""Printify ujung ke ujung: server sungguhan, Chromium sungguhan, Printify palsu. Tidak ada koneksi ke luar."""
import copy
import os
import threading
from urllib.parse import urlsplit

import pytest
from werkzeug.serving import make_server

from tests import printify_data as data
from tests.printify_fake import FakePrintify
from tests.test_web_smoke import free_port
from tests.web_helpers import printify_app, seed_ready_keyword, seeded_home

pytestmark = [pytest.mark.smoke,
              pytest.mark.skipif(not os.environ.get("CHROME_SMOKE_PATH"), reason="CHROME_SMOKE_PATH tidak diset")]


def test_printify_end_to_end(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    monkeypatch.setenv("HOME", str(tmp_path))
    home = seeded_home(tmp_path / "home")
    seed_ready_keyword(home)
    cheap_mug = copy.deepcopy(data.PRODUCTS_PAGE_2)
    cheap_mug["data"][0]["variants"][0]["cost"] = 100
    free_shipping = copy.deepcopy(data.SHIPPING[(68, 1)])
    free_shipping["profiles"][0]["first_item"]["cost"] = 0
    port = free_port()
    with FakePrintify() as fake:
        fake.load_default()
        fake.set("/v1/shops/111/products.json?page=2", cheap_mug)
        fake.set("/v1/catalog/blueprints/68/print_providers/1/shipping.json", free_shipping)
        app, _ = printify_app(home, fake, spawn=None, port=port)
        server = make_server("127.0.0.1", port, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        outside = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ["CHROME_SMOKE_PATH"])
                page = browser.new_page()

                def guard(route):
                    host = urlsplit(route.request.url).hostname
                    if host != "127.0.0.1":
                        outside.append(route.request.url)
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", guard)
                base = f"http://127.0.0.1:{port}"
                page.goto(base + "/printify")
                page.fill("#printify-token", "secret-tok-9876")
                page.click("text=Test and save")
                page.wait_for_selector("text=Sync now", timeout=10_000)
                page.click("text=Sync now")
                page.wait_for_selector("text=Your product", timeout=10_000)
                page.goto(base + "/opportunities?ready=1")
                assert page.locator("a.kw", has_text="custom mug").count() == 1
                assert page.locator(".badge--ready").count() >= 1
                browser.close()
        finally:
            server.shutdown()
        assert outside == []
