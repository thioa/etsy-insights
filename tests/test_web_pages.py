import re

import pytest

from etsy_insights.web import create_app
from etsy_insights.web.views import trend_points
from tests.web_helpers import TOKEN, FakeRunner, client, seed_printify, seed_ready_keyword, seeded_home


@pytest.fixture
def c(tmp_path):
    return client(create_app(seeded_home(tmp_path), token=TOKEN, runner=FakeRunner()))


def test_trend_points():
    assert trend_points([0, 100], width=100, height=110) == "0.0,110.0 100.0,10.0"
    assert trend_points([]) == ""


def test_session_page(c):
    html = c.get("/").get_data(as_text=True)
    assert f'content="{TOKEN}"' in html and "Start session" in html and "Test run (3 searches)" in html
    assert "Opportunities" in html and "My keywords" in html and "Peluang" not in html


def test_opportunities_filters_and_paging(c):
    html = c.get("/opportunities?label=Gold").get_data(as_text=True)
    labels = set(re.findall(r'data-label="(\w+)"', html))
    assert labels == {"Gold"} and "Download Excel" in html
    assert "custom address stamp" in c.get("/opportunities?q=address").get_data(as_text=True)
    page2 = c.get("/opportunities?label=Skip&page=2").get_data(as_text=True)
    assert 'aria-current="page">2<' in page2


def test_keyword_detail_searched_and_harvested(c):
    html = c.get("/keyword/sweatshirt").get_data(as_text=True)
    assert "Buyer taste" in html and "Popular themes" in html and "christmas" in html
    assert 'src="https://i.etsystatic.com/' in html and "Hard" in html and "<polyline" in html
    harvested = c.get("/keyword/gift%20for%20him").get_data(as_text=True)
    assert "Buyer taste appears after this keyword is searched" in harvested and "Prioritize" in harvested
    assert c.get("/keyword/nope-nope").status_code == 404


def test_keywords_and_settings_pages(c):
    html = c.get("/keywords").get_data(as_text=True)
    assert "Add keywords" in html and "Searched" in html and "No data" in html
    s = c.get("/settings").get_data(as_text=True)
    assert "Daily searches" in s and "1–30" in s and "Quit Etsy Insights" in s


def test_log_page_shows_latest_output(tmp_path):
    home = seeded_home(tmp_path)
    logs = home / "logs"
    logs.mkdir()
    old = logs / "sesi-20261110-100000.log"
    old.write_text("10:00:00 [1/15] mug\n", encoding="utf-8")
    new = logs / "session-20261111-100000.out"
    new.write_text("Google Chrome was not found. <install it>\n", encoding="utf-8")
    import os
    os.utime(old, (1, 1))
    c = client(create_app(home, token=TOKEN, runner=FakeRunner()))
    html = c.get("/log").get_data(as_text=True)
    assert "Google Chrome was not found. &lt;install it&gt;" in html and "session-20261111-100000.out" in html


def test_log_page_without_logs(c):
    assert "No session log yet." in c.get("/log").get_data(as_text=True)


def _row(html, keyword):
    match = re.search(r"<tr[^>]*>(?:(?!</tr>).)*>" + re.escape(keyword) + r"</a>(?:(?!</tr>).)*</tr>", html, re.S)
    assert match, keyword
    return match.group(0)


@pytest.fixture
def home(tmp_path):
    return seeded_home(tmp_path)


def test_opportunities_product_and_margin(home):
    seed_printify(home)
    c = client(create_app(home, token=TOKEN, runner=FakeRunner()))
    html = c.get("/opportunities?q=sweatshirt").get_data(as_text=True)
    sweat = _row(html, "sweatshirt")
    assert "Unisex Heavy Blend" in sweat and "-US$3.32" in sweat and "margin--bad" in sweat
    assert "Search to see price" in _row(html, "dog sweatshirt")
    assert "No match" in _row(c.get("/opportunities?q=personalized").get_data(as_text=True), "personalized")
    assert ">Product<" in html and ">Margin<" in html


def test_ready_filter_and_margin_sort(home):
    seed_ready_keyword(home)
    seed_printify(home, mug_cost=100, mug_shipping=0)
    c = client(create_app(home, token=TOKEN, runner=FakeRunner()))
    html = c.get("/opportunities?ready=1").get_data(as_text=True)
    assert "US$13.93 · 81.9%" in _row(html, "custom mug")
    assert ">sweatshirt</a>" not in html
    assert re.search(r'name="ready" value="1" checked', html) and "Ready to sell" in html
    html = c.get("/opportunities?sort=margin&dir=desc").get_data(as_text=True)
    margins = [None if m == "" else int(m) for m in re.findall(r'data-margin="(-?\d*)"', html)]
    known = [m for m in margins if m is not None]
    assert known[:2] == [1393, -332] and known == sorted(known, reverse=True)
    assert margins[:len(known)] == known


def test_keyword_detail_printify_panel(home):
    seed_printify(home)
    html = client(create_app(home, token=TOKEN, runner=FakeRunner())).get("/keyword/sweatshirt").get_data(as_text=True)
    for text in ("Printify", "Unisex Heavy Blend", "US$13.50", "US$4.75", "US$2.07", "-US$3.32",
                 "Price needed for a $5 margin", "US$26.19", "Link to product type", "Automatic"):
        assert text in html, text


def test_keyword_detail_search_to_see_price(home):
    seed_printify(home)
    html = client(create_app(home, token=TOKEN, runner=FakeRunner())).get("/keyword/dog sweatshirt").get_data(as_text=True)
    assert "Search to see price" in html and "Prioritize" in html


def test_settings_selling_section(c):
    html = c.get("/settings").get_data(as_text=True)
    for text in ("Selling on Etsy", "Etsy fees (% of sale)", "Fixed fee per sale (US$)", "Minimum margin (US$)"):
        assert text in html
