"""EtsyInsightsPage dengan Chromium asli. Semua URL Etsy dialihkan ke halaman/fixture palsu."""
import json
import os
import random
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest

from etsy_insights.browser import connected_browser, ensure_chrome
from etsy_insights.config import Config
from etsy_insights.insights_page import EtsyInsightsPage
from etsy_insights.models import NotLoggedIn, PageLoadTimeout
from etsy_insights.pacer import Pacer
from etsy_insights.parser import parse_search

pytestmark = [pytest.mark.smoke,
              pytest.mark.skipif(not os.environ.get("CHROME_SMOKE_PATH"), reason="CHROME_SMOKE_PATH tidak diset")]

PORT = 9342
_DRIVERS = []
FIX = json.loads((Path(__file__).parent / "fixtures" / "sweatshirt.json").read_text(encoding="utf-8"))
RESULTS_BODY = next(r["body"] for r in FIX["responses"] if "results-data" in r["url"])
ENQUEUE_BODY = next(r["body"] for r in FIX["responses"] if r["url"].endswith("/search/enqueue"))
DASH_HTML = ('<html><body><a data-app-key="marketplace-insights" '
             'href="/your/shops/me/marketplace-insights?ref=seller-platform-mcnav">Marketplace Insights</a></body></html>')
INSIGHTS_HTML = """<html><body><main><input aria-label="Input to search for keywords" type="text" size="40">
<script>
const i = document.querySelector('input');
i.addEventListener('keydown', async (e) => {
  if (e.key !== 'Enter') return;
  const q = encodeURIComponent(i.value);
  history.pushState(null, '', '/your/shops/me/marketplace-insights/search?query=' + q);
  await fetch('/api/v3/ajax/bespoke/shop/12345678/marketplace-insights/results-data?query=' + q +
              '&search_term_hash=&search_trigger=results_search_bar');
  await fetch('/api/v3/ajax/shop/12345678/marketplace-insights/llm-exploratory-keywords/search/enqueue',
              {method: 'POST'});
});
</script></main></body></html>"""
NO_INPUT_HTML = "<html><body><main><p>Tampilan baru</p></main></body></html>"
CAPTCHA_HTML = '<html><body><iframe src="https://geo.captcha-delivery.com/captcha/?x=1"></iframe></body></html>'


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    endpoint = ensure_chrome(PORT, tmp_path_factory.mktemp("prof"), Path(os.environ["CHROME_SMOKE_PATH"]),
                             ["--headless=new", "--no-sandbox"])
    try:
        with connected_browser(endpoint) as ctx:
            yield ctx
    finally:
        subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"])


@pytest.fixture
def state(context):
    st = {}

    def handler(route):
        path = urlparse(route.request.url).path
        if path == "/your/shops/me/dashboard":
            return route.fulfill(status=st.get("dashboard_status", 200), content_type="text/html", body=DASH_HTML)
        if path.startswith("/your/shops/me/marketplace-insights"):
            st["insights_hits"] = st.get("insights_hits", 0) + 1
            html = CAPTCHA_HTML if st.get("captcha") else NO_INPUT_HTML if st.get("no_input") else INSIGHTS_HTML
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path.endswith("/results-data"):
            body = st.get("results_body", RESULTS_BODY)
            return route.fulfill(status=st.get("results_status", 200), content_type="application/json",
                                 body=json.dumps(body))
        if path.endswith("/search/poll"):
            return route.fulfill(status=st.get("poll_status", 200), content_type="application/json", body="null")
        if path == "/signin":
            return route.fulfill(status=200, content_type="text/html", body="<h1>Sign in</h1>")
        if path.endswith("/search/enqueue"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(ENQUEUE_BODY))
        return route.fulfill(status=404, body="")

    def blank(route):
        route.fulfill(status=200, content_type="text/html", body="<p>captcha</p>")

    context.route("https://www.etsy.com/**", handler)
    context.route("https://geo.captcha-delivery.com/**", blank)
    yield st
    while _DRIVERS:
        _DRIVERS.pop().close()
    context.unroute("https://www.etsy.com/**")
    context.unroute("https://geo.captcha-delivery.com/**")
    for p in list(context.pages):
        p.close()


def make_page(context, **kw):
    pacer = Pacer(Config(kecepatan_ketik_ms=(1, 1)), random.Random(1))
    driver = EtsyInsightsPage(context, pacer, random.Random(1), settle_seconds=(0, 0), input_timeout=1,
                              results_timeout=5, related_timeout=2, **kw)
    _DRIVERS.append(driver)
    return driver


def test_open_and_search_returns_parsable_results(context, state):
    page = make_page(context)
    page.open()
    raw = page.search("sweatshirt")
    parsed = parse_search(raw)
    assert parsed.main.search_volume == 46395 and len(parsed.related) == 180
    assert page.check_danger() is None
    assert "marketplace-insights" in raw.page_url
    tab = [p for p in context.pages if "marketplace-insights" in p.url][-1]
    assert tab.input_value('input[aria-label="Input to search for keywords"]') == "sweatshirt"


def test_open_not_logged_in(context, state):
    with pytest.raises(NotLoggedIn):
        make_page(context, dashboard_url="https://www.etsy.com/signin?from=test").open()


def test_captcha_frame_detected(context, state):
    state["captcha"] = True
    page = make_page(context)
    page.open()
    assert page.check_danger().kind == "captcha"


def test_http_429_detected_quickly(context, state):
    state["results_status"] = 429
    page = make_page(context)
    page.open()
    started = time.monotonic()
    page.search("sweatshirt")
    assert time.monotonic() - started < 5 and page.check_danger().kind == "http_429"


def test_search_box_missing_raises_page_load_timeout(context, state):
    state["no_input"] = True
    page = make_page(context)
    page.open()
    with pytest.raises(PageLoadTimeout):
        page.search("x")


def test_late_429_blocks_next_search(context, state):
    page = make_page(context)
    page.open()
    page.search("sweatshirt")
    assert page.check_danger() is None
    state["poll_status"] = 429
    tab = [p for p in context.pages if "marketplace-insights" in p.url][-1]
    tab.evaluate("() => fetch('/api/v3/ajax/shop/12345678/marketplace-insights/llm-exploratory-keywords/search/poll')"
                 ".then(r => r.status)")
    page.search("mug")
    assert tab.input_value('input[aria-label="Input to search for keywords"]') == "sweatshirt"
    assert page.check_danger().kind == "http_429"


def test_open_stops_on_blocked_dashboard(context, state):
    state["dashboard_status"] = 403
    page = make_page(context)
    started = time.monotonic()
    page.open()
    assert time.monotonic() - started < 5 and state.get("insights_hits", 0) == 0
    assert page.check_danger().kind == "http_403"


def test_quota_flags_end_wait_early(context, state):
    from etsy_insights.models import EtsyQuotaReached
    state["results_body"] = {"isQuotaReached": True, "isSearchAllowed": False,
                             "quotaData": {"totalQuota": 15, "remainingQuota": 0, "lowRemainingQuotaThreshold": 5}}
    page = make_page(context)
    page.open()
    started = time.monotonic()
    raw = page.search("mug")
    assert time.monotonic() - started < 3
    with pytest.raises(EtsyQuotaReached):
        parse_search(raw)


def test_keyword_with_signin_text_works(context, state):
    page = make_page(context)
    page.open()
    assert parse_search(page.search("book signing")).main.search_volume == 46395


def test_close_closes_its_tab(context, state):
    page = make_page(context)
    page.open()
    before = len(context.pages)
    page.close()
    assert len(context.pages) == before - 1
