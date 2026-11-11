import pytest
from openpyxl import load_workbook

from etsy_insights.config import Config
from etsy_insights.export import ALL_DATA_HEADERS, OPPORTUNITIES_HEADERS, QUEUE_HEADERS, TASTE_HEADERS, export_excel
from etsy_insights.planner import upcoming
from etsy_insights.score import score_all
from etsy_insights.store import Store
from etsy_insights.taste import build_profile
from tests.helpers import T0, make_metrics, make_raw, make_related, make_row
from tests.test_parser import load_raw

ROWS = [make_row("a", 1000, 3, 100, wow=12.0, rate=0.00022), make_row("b", 500, 2, 1000),
        make_row("c", 2000, 1, 5000, source="related", parent="a", row_kind="panen"),
        make_row("e", 4000, 4, 10), make_row("d", 50, 4, 1)]


def test_export_peluang_sheet(tmp_path):
    path = export_excel(score_all(ROWS, Config()), ROWS, [], tmp_path, T0.date())
    ws = load_workbook(path)["Opportunities"]
    assert [c.value for c in ws[2]] == OPPORTUNITIES_HEADERS and ws.freeze_panes == "A3"
    assert [ws.cell(r, 1).value for r in range(3, 7)] == ["e", "a", "c", "b"]
    row_a = [c.value for c in ws[4]]
    assert row_a[3] == "High" and row_a[4] == pytest.approx(0.00022) and row_a[8] == "+12.0%"
    assert row_a[9] == "Your list"
    assert ws.cell(4, 5).number_format == "0.000%" and ws.cell(5, 10).value == "Harvested from: a"
    assert ws.cell(3, 8).value == "Gold" and ws.cell(3, 8).fill.fgColor.rgb.endswith("FFD966")


def test_export_semua_data_indonesian_status(tmp_path):
    ws = load_workbook(export_excel(score_all(ROWS, Config()), ROWS, [], tmp_path, T0.date()))["All data"]
    assert [c.value for c in ws[2]] == ALL_DATA_HEADERS
    by_kw = {ws.cell(r, 1).value: [c.value for c in ws[r]] for r in range(3, ws.max_row + 1)}
    assert by_kw["c"][1:3] == ["Harvested", "Harvested"] and by_kw["a"][1:3] == ["Searched", "Searched"]


def test_export_text_is_safe(tmp_path):
    rows = [make_row("=sum(", 1000, 2, 10), make_row("bad\x01kw", 900, 2, 10)]
    ws = load_workbook(export_excel(score_all(rows, Config()), rows, [], tmp_path, T0.date()))["Opportunities"]
    cells = {ws.cell(r, 1).value: ws.cell(r, 1) for r in range(3, ws.max_row + 1)}
    assert cells["=sum("].data_type == "s" and "badkw" in cells


def test_export_empty(tmp_path):
    wb = load_workbook(export_excel([], [], [], tmp_path, T0.date()))
    assert "0 keywords ranked" in wb["Opportunities"]["A1"].value
    assert [c.value for c in wb["Opportunities"][2]] == OPPORTUNITIES_HEADERS
    assert [c.value for c in wb["Queue"][2]] == QUEUE_HEADERS


def test_export_queue_sheet(tmp_path):
    s = Store(":memory:")
    s.sync_user_keywords(["a", "b"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    s.save_harvest(s.get("a").id, [make_related("x", 5000, 50, 4)], 200, 2, T0)
    ws = load_workbook(export_excel([], [], upcoming(s, Config()), tmp_path, T0.date()))["Queue"]
    assert [c.value for c in ws[3]] == [1, "b", "Your list", 0, None]
    assert [c.value for c in ws[4]] == [2, "x", "Harvested", 1, "a"]


def test_export_selera_sheet(tmp_path):
    rows = [make_row("sweatshirt", 46395, 0, 1863632), make_row("mug", 900, 2, 500)]
    profiles = {"sweatshirt": build_profile(load_raw("sweatshirt"))}
    wb = load_workbook(export_excel(score_all(rows, Config()), rows, [], tmp_path, T0.date(), profiles=profiles))
    assert wb.sheetnames == ["Opportunities", "Buyer taste", "All data", "Queue"]
    sel = wb["Buyer taste"]
    assert [c.value for c in sel[2]] == TASTE_HEADERS and sel.max_row == 3
    row = {h: sel.cell(3, i + 1) for i, h in enumerate(TASTE_HEADERS)}
    assert row["Keyword"].value == "sweatshirt" and row["Price buyers pay"].value == "US$15.30 – US$18.70"
    assert row["Entry difficulty"].value == "Hard"
    assert row["Listing 1"].hyperlink.target.startswith("https://www.etsy.com/listing/")
    pel = wb["Opportunities"]
    by_kw = {pel.cell(r, 1).value: [c.value for c in pel[r]] for r in range(3, pel.max_row + 1)}
    assert by_kw["sweatshirt"][-2:] == ["US$15.30 – US$18.70", "Hard"] and by_kw["mug"][-2:] == [None, None]
