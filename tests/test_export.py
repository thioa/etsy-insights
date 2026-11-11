import pytest
from openpyxl import load_workbook

from etsy_insights.config import Config
from etsy_insights.export import ANTREAN_HEADERS, PELUANG_HEADERS, SEMUA_HEADERS, export_excel
from etsy_insights.planner import upcoming
from etsy_insights.score import score_all
from etsy_insights.store import Store
from tests.helpers import T0, make_metrics, make_raw, make_related, make_row

ROWS = [make_row("a", 1000, 3, 100, wow=12.0, rate=0.00022), make_row("b", 500, 2, 1000),
        make_row("c", 2000, 1, 5000, source="related", parent="a", row_kind="panen"),
        make_row("e", 4000, 4, 10), make_row("d", 50, 4, 1)]


def test_export_peluang_sheet(tmp_path):
    path = export_excel(score_all(ROWS, Config()), ROWS, [], tmp_path, T0.date())
    ws = load_workbook(path)["Peluang"]
    assert [c.value for c in ws[2]] == PELUANG_HEADERS and ws.freeze_panes == "A3"
    assert [ws.cell(r, 1).value for r in range(3, 7)] == ["e", "a", "c", "b"]
    row_a = [c.value for c in ws[4]]
    assert row_a[3] == "Tinggi" and row_a[4] == pytest.approx(0.00022) and row_a[8] == "+12.0%"
    assert row_a[9] == "daftar Anda"
    assert ws.cell(4, 5).number_format == "0.000%" and ws.cell(5, 10).value == "panen dari: a"
    assert ws.cell(3, 8).value == "Emas" and ws.cell(3, 8).fill.fgColor.rgb.endswith("FFD966")


def test_export_semua_data_indonesian_status(tmp_path):
    ws = load_workbook(export_excel(score_all(ROWS, Config()), ROWS, [], tmp_path, T0.date()))["Semua data"]
    assert [c.value for c in ws[2]] == SEMUA_HEADERS
    by_kw = {ws.cell(r, 1).value: [c.value for c in ws[r]] for r in range(3, ws.max_row + 1)}
    assert by_kw["c"][1:3] == ["panen", "hasil panen"] and by_kw["a"][1:3] == ["dicari", "sudah dicari"]


def test_export_text_is_safe(tmp_path):
    rows = [make_row("=sum(", 1000, 2, 10), make_row("bad\x01kw", 900, 2, 10)]
    ws = load_workbook(export_excel(score_all(rows, Config()), rows, [], tmp_path, T0.date()))["Peluang"]
    cells = {ws.cell(r, 1).value: ws.cell(r, 1) for r in range(3, ws.max_row + 1)}
    assert cells["=sum("].data_type == "s" and "badkw" in cells


def test_export_empty(tmp_path):
    wb = load_workbook(export_excel([], [], [], tmp_path, T0.date()))
    assert "0 keyword layak" in wb["Peluang"]["A1"].value
    assert [c.value for c in wb["Peluang"][2]] == PELUANG_HEADERS
    assert [c.value for c in wb["Antrean"][2]] == ANTREAN_HEADERS


def test_export_queue_sheet(tmp_path):
    s = Store(":memory:")
    s.sync_user_keywords(["a", "b"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    s.save_harvest(s.get("a").id, [make_related("x", 5000, 50, 4)], 200, 2, T0)
    ws = load_workbook(export_excel([], [], upcoming(s, Config()), tmp_path, T0.date()))["Antrean"]
    assert [c.value for c in ws[3]] == [1, "b", "daftar Anda", 0, None]
    assert [c.value for c in ws[4]] == [2, "x", "hasil panen", 1, "a"]
