"""Katalog ujung ke ujung: server sungguhan, Chromium sungguhan, Printify palsu (HTTPS lokal, dengan foto)."""
import copy
import os
import ssl
import subprocess
import threading
from urllib.parse import urlsplit

import pytest
from werkzeug.serving import make_server

from tests import printify_data as data
from tests.printify_fake import FakePrintify
from tests.test_web_smoke import free_port
from tests.web_helpers import printify_app, seeded_home
from tools.build_app import _png

pytestmark = [pytest.mark.smoke,
              pytest.mark.skipif(not os.environ.get("CHROME_SMOKE_PATH"), reason="CHROME_SMOKE_PATH tidak diset")]


def test_catalog_end_to_end(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    monkeypatch.setenv("HOME", str(tmp_path))
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "2", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    home = seeded_home(tmp_path / "home")
    port = free_port()
    with FakePrintify(tls=(cert, key)) as fake:
        fake.load_default()
        blueprints = copy.deepcopy(data.BLUEPRINTS)
        blueprints[0]["images"] = [fake.url + "/img/sweat.png"]
        fake.set("/v1/catalog/blueprints.json", blueprints)
        fake.set("/img/sweat.png", _png(64), headers={"Content-Type": "image/png"})
        app, _ = printify_app(home, fake, spawn=None, port=port,
                              ssl_context=ssl.create_default_context(cafile=str(cert)))
        server = make_server("127.0.0.1", port, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        outside = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ["CHROME_SMOKE_PATH"])
                page = browser.new_context(ignore_https_errors=True).new_page()

                def guard(route):
                    if urlsplit(route.request.url).hostname != "127.0.0.1":
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

                page.goto(base + "/catalog")
                photo = page.locator("article[data-category='sweatshirt'] img")
                photo.wait_for(timeout=5_000)
                page.wait_for_function("img => img.complete && img.naturalWidth > 0", arg=photo.element_handle(),
                                       timeout=5_000)
                tees = page.locator("article[data-category='t shirt']")
                tees.locator("text=Research").click()
                page.wait_for_selector("article[data-category='t shirt'] >> text=In queue: 3 keywords", timeout=10_000)
                page.locator("article[data-category='t shirt'] >> text=View products").click()
                product = page.locator("[data-blueprint='384']")
                product.locator("text=Choose provider").click()
                product.locator("[data-provider]").select_option("29")
                page.wait_for_selector("[data-blueprint='384'] >> text=US shipping: No US shipping", timeout=10_000)
                product.locator("[data-cost]").fill("4.80")
                product.locator("text=Add to my product types").click()
                page.wait_for_selector("[data-blueprint='384'] >> text=In my products", timeout=10_000)
                page.goto(base + "/printify")
                assert page.locator("text=Unisex Jersey Short Sleeve Tee").count() >= 1
                browser.close()
        finally:
            server.shutdown()
        assert outside == []
