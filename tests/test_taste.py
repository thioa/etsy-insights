import pytest

from etsy_insights.taste import build_profile, difficulty, parse_price, top_terms
from tests.test_parser import load_raw


def test_parse_price():
    assert parse_price("Rp 712,738") == 712738.0 and parse_price("US$15.30") == 15.3
    assert parse_price("") is None and parse_price(None) is None


def test_top_terms_prefers_phrases():
    titles = ["Retro Christmas Sweater Gift", "Retro Christmas Mug", "Vintage Retro Tee"]
    assert top_terms(titles, "sweater") == [("retro", 3), ("retro christmas", 2)]


def test_difficulty_rules():
    assert difficulty(2500, 0.1, 0.1) == "Hard" and difficulty(1200, 0.85, 0.0) == "Hard"
    assert difficulty(250, 0.3, 0.9) == "Easy" and difficulty(650, 1.0, 0.5) == "Medium"
    assert difficulty(None, 0.0, 0.0) == "Unknown"


def test_profile_sweatshirt():
    p = build_profile(load_raw("sweatshirt"))
    assert (p.listing_count, p.paid_price_low, p.paid_price_high) == (19, "US$15.30", "US$18.70")
    assert (p.median_reviews, p.unique_shops, p.difficulty) == (2362, 18, "Hard")
    assert p.bestseller_share == pytest.approx(16 / 19) and p.star_seller_share == pytest.approx(16 / 19)
    terms = [t for t, _ in p.top_terms]
    assert "christmas" in terms[:3] and not any("sweatshirt" in t for t in terms)
    assert len(p.examples) == 5 and p.examples[0].title.startswith("Oh What Fun Christmas Sweatshirt")
    assert p.examples[0].url.startswith("https://www.etsy.com/listing/")


def test_profile_custom_and_personalized_difficulty():
    assert build_profile(load_raw("custom")).difficulty == "Medium"
    assert build_profile(load_raw("personalized")).difficulty == "Hard"


def test_profile_none_without_cards():
    assert build_profile(load_raw("swearshirt")) is None
