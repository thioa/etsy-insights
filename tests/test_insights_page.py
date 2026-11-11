from etsy_insights.insights_page import detect_danger, has_related_for, has_results_for
from tests.test_parser import load_raw


def test_detect_danger_cases():
    assert detect_danger("https://www.etsy.com/signin?from=x", [], "", []).kind == "login"
    assert detect_danger("https://www.etsy.com/your/shops/me/marketplace-insights",
                         ["https://geo.captcha-delivery.com/captcha/?a=1"], "", []).kind == "captcha"
    assert detect_danger("https://www.etsy.com/x", [], "Please verify you are a human", []).kind == "verifikasi"
    assert detect_danger("https://www.etsy.com/x", [], "", [200, 429]).kind == "http_429"
    assert detect_danger("https://www.etsy.com/x", [], "", [403]).kind == "http_403"
    assert detect_danger("https://www.etsy.com/your/shops/me/marketplace-insights", [], "Searches 43k", [200]) is None


def test_has_results_for():
    raw = load_raw("custom")
    assert has_results_for(raw.responses, "custom") and not has_results_for(raw.responses, "hoodie")


def test_has_related_for_ignores_stale_poll():
    raw = load_raw("sweatshirt")
    stale_only = tuple(r for r in raw.responses if "enqueue" not in r.url)
    assert has_related_for(raw.responses, "sweatshirt") and not has_related_for(stale_only, "sweatshirt")


def test_login_and_captcha_markers_ignore_query_string():
    base = "https://www.etsy.com/your/shops/me/marketplace-insights/search?query="
    assert detect_danger(base + "book+signing", [], "", []) is None
    assert detect_danger(base + "captcha+kit", [], "", []) is None
    assert detect_danger("https://www.etsy.com/signin?from_page=x", [], "", []).kind == "login"


class _Ctx:
    def on(self, *args):
        pass


class _NavigatingPage:
    def __init__(self, url):
        self.url, self.frames, self.waits = url, [], 0

    def evaluate(self, script):
        from playwright.sync_api import Error
        raise Error("Page.evaluate: Execution context was destroyed, most likely because of a navigation")

    def wait_for_timeout(self, ms):
        self.waits += 1


def _driver_on(url):
    import random
    from etsy_insights.config import Config
    from etsy_insights.insights_page import EtsyInsightsPage
    from etsy_insights.pacer import Pacer
    driver = EtsyInsightsPage(_Ctx(), Pacer(Config(), random.Random(1)), random.Random(1))
    driver._page = _NavigatingPage(url)
    return driver


def test_check_danger_survives_navigation():
    assert _driver_on("https://www.etsy.com/signin?from=x").check_danger().kind == "login"
    driver = _driver_on("https://www.etsy.com/your/shops/me/marketplace-insights")
    assert driver.check_danger() is None and driver._page.waits >= 2
