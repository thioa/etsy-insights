from openpyxl import load_workbook

from etsy_insights.config import Config
from etsy_insights.export import ANTREAN_HEADERS, PELUANG_HEADERS, SEMUA_HEADERS, export_excel
from etsy_insights.score import score_all
from etsy_insights.store import Store
from tests.helpers import T0, make_row


def test_export_sheets_order_and_colors(tmp_path):
    rows = [make_row("a", 1000, 0.05, 100, trend=(100, 112)), make_row("b", 500, 0.03, 1000),
            make_row("c", 2000, 0.01, 5000, source="related", parent="a"),
            make_row("e", 4000, 0.09, 10), make_row("d", 50, 0.1, 1)]
    scored = score_all(rows, Config())
    path = export_excel(scored, rows, [], tmp_path / "hasil", T0.date())
    assert path.name == "peluang-2026-11-11.xlsx"
    wb = load_workbook(path)
    assert wb.sheetnames == ["Peluang", "Semua data", "Antrean"]
    ws = wb["Peluang"]
    assert [c.value for c in ws[2]] == PELUANG_HEADERS and ws.freeze_panes == "A3"
    assert "4 keyword layak" in ws["A1"].value and "Data masih sedikit" in ws["A1"].value
    assert [ws.cell(r, 1).value for r in range(3, 7)] == ["e", "a", "c", "b"]
    assert ws.cell(3, 7).value == "Emas" and ws.cell(3, 7).fill.fgColor.rgb.endswith("FFD966")
    assert ws.cell(4, 8).value == "+12%" and ws.cell(5, 9).value == "terkait dari: a"
    assert ws.cell(4, 3).number_format == "0.0%"
    semua = wb["Semua data"]
    assert [c.value for c in semua[2]] == SEMUA_HEADERS and semua.max_row == 2 + 5


def test_export_empty(tmp_path):
    path = export_excel([], [], [], tmp_path, T0.date())
    wb = load_workbook(path)
    assert "0 keyword layak" in wb["Peluang"]["A1"].value
    assert [c.value for c in wb["Antrean"][2]] == ANTREAN_HEADERS


def test_export_queue_sheet(tmp_path):
    s = Store(":memory:")
    s.sync_user_keywords(["a"], T0)
    s.add_related(s.get("a").id, ["b"], 10, 2, T0)
    ws = load_workbook(export_excel([], [], s.pending_queue(), tmp_path, T0.date()))["Antrean"]
    assert [ws.cell(3, c).value for c in (1, 2, 3)] == ["a", "daftar Anda", 0]
    assert [ws.cell(4, c).value for c in (1, 2, 4)] == ["b", "terkait", "a"]
