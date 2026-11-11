from types import SimpleNamespace

from etsy_insights.config import Config
from etsy_insights.margin import NO_MATCH, Fees
from etsy_insights.printify_store import ProductType
from etsy_insights.product_fit import fees_from_config, fit_all, fit_keyword, match_counts, minimum_cents

FEES = Fees(9.5, 45)


def pt(type_id, title, source, cost, ship, words, available=True):
    return ProductType(type_id, type_id, 1, title, "Prov", source, cost, cost, ship, 3, tuple(words), False,
                       available, None)


A = pt(1, "A", "picked", 1241, 475, ["sweatshirt"])
B = pt(2, "B", "own", 1241, 475, ["sweatshirt"])
C = pt(3, "C", "own", 1500, 475, ["sweatshirt"])
MUG = pt(5, "Mug", "own", 512, 699, ["mug"])


def scored(keyword, label):
    return SimpleNamespace(row=SimpleNamespace(keyword=keyword), label=label)


def test_best_margin_wins_and_ties_prefer_own():
    fit = fit_keyword("custom sweatshirt", "Gold", 3000, [A, C, B], None, FEES, 500)
    assert fit.primary.id == 2 and fit.margin.margin_cents == 954 and fit.ready and not fit.linked
    assert [c.type.id for c in fit.candidates] == [2, 1, 3]


def test_no_match_and_unavailable():
    fit = fit_keyword("gift for mom", "Gold", 3000, [B], None, FEES, 500)
    assert fit.margin is NO_MATCH and fit.primary is None and fit.candidates == () and not fit.ready
    off = pt(4, "Off", "picked", 100, 0, ["sweatshirt"], available=False)
    assert fit_keyword("sweatshirt", "Gold", 3000, [off], None, FEES, 500).margin is NO_MATCH


def test_link_overrides_automatic():
    fit = fit_keyword("gift for mom", "Gold", 3000, [B, MUG], 5, FEES, 500)
    assert [c.type.id for c in fit.candidates] == [5] and fit.linked and fit.primary.id == 5
    assert [c.type.id for c in fit_keyword("custom sweatshirt", "Gold", 3000, [B, MUG], 5, FEES, 500).candidates] == [5]


def test_no_price_picks_own_then_cheapest():
    cheap_picked = pt(6, "P", "picked", 900, 475, ["sweatshirt"])
    fit = fit_keyword("sweatshirt", "Gold", None, [cheap_picked, C, B], None, FEES, 500)
    assert fit.margin.status == "no_price" and fit.primary.id == 2 and not fit.ready


def test_ready_follows_label():
    assert fit_keyword("sweatshirt", "Gold", 3000, [B], None, FEES, 500).ready
    assert not fit_keyword("sweatshirt", "Skip", 3000, [B], None, FEES, 500).ready


def test_fit_all_uses_profile_price_and_config():
    sweat = pt(7, "Sweatshirt", "own", 1350, 475, ["sweatshirt"])
    profiles = {"sweatshirt": SimpleNamespace(paid_price_low="US$15.30", paid_price_high="US$18.70")}
    fits = fit_all([scored("sweatshirt", "Skip"), scored("custom sweatshirt", "Gold")], profiles, [sweat], {}, Config())
    assert fits["sweatshirt"].margin.margin_cents == -332 and fits["sweatshirt"].margin.price_needed_cents == 2619
    assert fits["custom sweatshirt"].margin.status == "no_price"
    assert fees_from_config(Config()) == Fees(9.5, 45) and minimum_cents(Config()) == 500


def test_match_counts():
    assert match_counts(["custom sweatshirt", "sweatshirts", "mug", "gift"], [B, MUG], {"gift": 5}) == {2: 2, 5: 2}
