import re

import pytest

from etsy_insights.web import create_app
from etsy_insights.web.views import trend_points
from tests.web_helpers import TOKEN, FakeRunner, client, seeded_home


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
