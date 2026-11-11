import re

import pytest

from etsy_insights.printify_store import Blueprint
from etsy_insights.web import create_app
from tests.web_helpers import TOKEN, FakeRunner, client, seed_printify, seed_ready_keyword, seeded_home


@pytest.fixture
def home(tmp_path):
    return seeded_home(tmp_path)


def page(home, path):
    return client(create_app(home, token=TOKEN, runner=FakeRunner())).get(path)


def card(html, name):
    match = re.search(r'<article class="category-card"(?:(?!</article>).)*>' + re.escape(name) + r'</h2>(?:(?!</article>).)*</article>',
                      html, re.S)
    assert match, name
    return match.group(0)


def card_names(html):
    return re.findall(r'<h2 class="category-card__name">([^<]+)</h2>', html)


def test_catalog_without_sync(home):
    html = page(home, "/catalog").get_data(as_text=True)
    assert "Connect Printify and run Sync to load the catalog." in html and 'href="/printify"' in html
    assert 'href="/catalog"' in html


def test_catalog_cards(home):
    seed_ready_keyword(home)
    seed_printify(home, mug_cost=100, mug_shipping=0)
    html = page(home, "/catalog").get_data(as_text=True)
    for text in ("Printify catalog", "Most searched:", "Opportunities:", "Uses up to 3 of your daily searches.",
                 'data-api="/api/catalog/research"'):
        assert text in html
    mugs, sweat = card(html, "Mugs"), card(html, "Sweatshirts")
    assert "Ready to sell: 1" in mugs and "1 product" in mugs and "No photo" in mugs and "In my products" in mugs
    assert 'loading="lazy"' in sweat and 'src="https://images.printify.com/sweat.png"' in sweat
    assert "Run Sync to load product photos." not in html
    seed_printify(home, blueprints=[Blueprint(68, "Accent Coffee Mug, 11oz", "Generic brand", "", "")])
    assert "Run Sync to load product photos." in page(home, "/catalog").get_data(as_text=True)


def test_catalog_search_and_filters(home):
    seed_printify(home)
    assert card_names(page(home, "/catalog?q=Necklace!").get_data(as_text=True)) == ["Necklaces"]
    not_researched = card_names(page(home, "/catalog?status=not_researched").get_data(as_text=True))
    assert "Pet bowls" in not_researched and "Sweatshirts" not in not_researched
    assert set(card_names(page(home, "/catalog?mine=1").get_data(as_text=True))) == {"Sweatshirts", "Mugs"}
    names = card_names(page(home, "/catalog?sort=name").get_data(as_text=True))
    assert names[:-1] == sorted(names[:-1]) and names[-1] == "Other"


def test_category_page(home):
    seed_ready_keyword(home)
    seed_printify(home, mug_cost=100, mug_shipping=0)
    html = page(home, "/catalog/mug").get_data(as_text=True)
    for text in ("Mugs", "Keywords with data", "Most searched", "Opportunities", "Ready to sell", "Top keywords",
                 'href="/keyword/custom%20mug"', 'href="/opportunities?q=mug"', "Choose provider", "In my products",
                 "Generic brand", 'data-blueprint="68"'):
        assert text in html, text


def test_unknown_category_page(home):
    seed_printify(home)
    r = page(home, "/catalog/nope")
    assert r.status_code == 404 and "Unknown category." in r.get_data(as_text=True)
    assert page(home, "/catalog/pet-bowl").status_code == 200


def test_titles_are_escaped(home):
    seed_printify(home, blueprints=[Blueprint(68, "<script>alert(1)</script> Mug", "B", "", "")])
    assert "<script>alert" not in page(home, "/catalog?q=script").get_data(as_text=True)  # judul hanya untuk pencarian
    html = page(home, "/catalog/mug").get_data(as_text=True)
    assert "<script>alert" not in html and "&lt;script&gt;alert(1)&lt;/script&gt; Mug" in html


def test_category_page_reuses_the_catalog_summary(home, monkeypatch):
    import etsy_insights.catalog as catalog
    seed_ready_keyword(home)
    seed_printify(home, mug_cost=100, mug_shipping=0)
    calls = []
    real = catalog.score_all
    monkeypatch.setattr(catalog, "score_all", lambda rows, cfg: calls.append(1) or real(rows, cfg))
    c = client(create_app(home, token=TOKEN, runner=FakeRunner()))
    c.get("/catalog")
    html = c.get("/catalog/mug").get_data(as_text=True)
    assert len(calls) == 1 and 'href="/keyword/custom%20mug"' in html
