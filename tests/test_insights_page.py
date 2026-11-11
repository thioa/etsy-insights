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
