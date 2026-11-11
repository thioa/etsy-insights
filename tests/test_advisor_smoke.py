"""AI Advisor ujung ke ujung: server sungguhan, Chromium sungguhan, Anthropic palsu (HTTP lokal), thread sungguhan."""
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from werkzeug.serving import make_server

from etsy_insights.advisor_ai import AdvisorAI
from tests.advisor_helpers import ANSWER, KEY, advisor_home
from tests.anthropic_fake import FakeAnthropic, search_blocks, stream, text_block
from tests.test_web_smoke import free_port
from tests.web_helpers import advisor_app

pytestmark = [pytest.mark.smoke,
              pytest.mark.skipif(not os.environ.get("CHROME_SMOKE_PATH"), reason="CHROME_SMOKE_PATH tidak diset")]


def test_advisor_end_to_end(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    monkeypatch.setenv("HOME", str(tmp_path))
    home = advisor_home(tmp_path, key=False)
    port = free_port()
    with FakeAnthropic() as fake:
        trends = search_blocks("etsy gift trends", [("https://news.example/valentine", "Valentine gift guide")])
        trends.append(text_block("- Valentine's Day: list couple mugs by Jan 15.",
                                 citations=[("https://news.example/valentine", "Valentine gift guide")]))
        fake.queue("POST", "/v1/messages", stream(trends, web_searches=1),
                   stream([text_block(json.dumps(ANSWER))], input_tokens=20_000, output_tokens=3_000))
        app, _ = advisor_app(home, lambda key: AdvisorAI(key, base_url=fake.url, trust_env=False, max_retries=0),
                             spawn=None, port=port)
        server = make_server("127.0.0.1", port, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        outside = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ["CHROME_SMOKE_PATH"])
                page = browser.new_context(device_scale_factor=2, viewport={"width": 1280, "height": 900}).new_page()

                def guard(route):
                    if urlsplit(route.request.url).hostname != "127.0.0.1":
                        outside.append(route.request.url)
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", guard)
                page.on("dialog", lambda dialog: dialog.accept())
                base = f"http://127.0.0.1:{port}"
                page.goto(base + "/advisor")
                page.fill("#advisor-key", KEY)
                page.click("text=Save and test")
                page.wait_for_selector("[data-advisor-run]", timeout=10_000)
                page.click("[data-advisor-run]")
                page.wait_for_selector("text=Backed by data", timeout=20_000)
                assert "/advisor/" in page.url
                shots = os.environ.get("SMOKE_SCREENSHOT_DIR")
                if shots:
                    page.screenshot(path=str(Path(shots) / "advisor-report.png"), full_page=True)
                row = page.locator("[data-idea='cat dad mug']")
                row.locator("[data-idea-check]").check()
                page.click("text=Add selected to queue")
                page.wait_for_selector("[data-idea='cat dad mug'] >> text=In queue", timeout=10_000)
                page.goto(base + "/keywords")
                assert page.locator("text=cat dad mug").count() >= 1
                browser.close()
        finally:
            server.shutdown()
        assert outside == []
        assert len(fake.messages()) == 2
