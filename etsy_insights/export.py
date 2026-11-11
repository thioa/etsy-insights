"""Menulis hasil ke file Excel."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import QueueItem, ResultRow
from .score import LEVEL_LABELS, ScoredKeyword

PELUANG_HEADERS = ["Keyword", "Volume pencarian", "Conversion rate", "Kompetisi", "Pencarian per listing",
                   "Skor", "Label", "Tren", "Asal keyword", "Tanggal cek"]
SEMUA_HEADERS = ["Keyword", "Status", "Tanggal cek", "Volume pencarian", "Conversion rate", "Kompetisi",
                 "Jenis kompetisi", "Keyword terkait", "Label terbaru"]
ANTREAN_HEADERS = ["Keyword", "Sumber", "Kedalaman", "Asal keyword", "Ditambahkan"]
LABEL_FILLS = {"Emas": "FFD966", "Potensial": "C6EFCE", "Lewati": "D9D9D9"}

_FEW_DATA = 10
_PERCENT = "0.0%"
_COMPETITION_KIND_TEXT = {"count": "jumlah listing", "level": "level"}


def _local_date(dt: datetime) -> str:
    return dt.astimezone().date().isoformat()


def _competition(row: ResultRow):
    m = row.metrics
    if m.competition_value is None:
        return None
    if m.competition_kind == "level":
        return LEVEL_LABELS.get(int(m.competition_value), m.competition_value)
    return m.competition_value


def _trend_text(trend: tuple[float, ...]) -> str:
    if len(trend) >= 2 and trend[0] > 0:
        return f"{(trend[-1] - trend[0]) / trend[0]:+.0%}"
    return ""


def _origin(row: ResultRow) -> str:
    return "daftar Anda" if row.source == "user" else f"terkait dari: {row.parent_keyword}"


def _write_table(ws: Worksheet, info: str, headers: list[str], rows: list[list],
                 widths: list[int], percent_cols: Sequence[int] = ()) -> None:
    ws["A1"] = info
    ws["A1"].font = Font(italic=True)
    ws.append(headers)
    for cell in ws[2]:
        cell.font = Font(bold=True)
    for values in rows:
        ws.append(values)
    for col in percent_cols:
        for r in range(3, ws.max_row + 1):
            ws.cell(r, col).number_format = _PERCENT
    last_col = get_column_letter(len(headers))
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{last_col}{max(2, ws.max_row)}"
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def export_excel(scored: Sequence[ScoredKeyword], history: Sequence[ResultRow],
                 queue: Sequence[QueueItem], out_dir: Path, today: date) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"peluang-{today.isoformat()}.xlsx"

    wb = Workbook()
    peluang = wb.active
    peluang.title = "Peluang"
    ranked = [s for s in scored if s.eligible]
    info = f"Diperbarui {today}. {len(ranked)} keyword layak dirank."
    if len(ranked) < _FEW_DATA:
        info += " Data masih sedikit (< 10 keyword layak), peringkat masih kasar."
    _write_table(
        peluang, info, PELUANG_HEADERS,
        [[s.row.keyword, s.row.metrics.search_volume, s.row.metrics.conversion_rate, _competition(s.row),
          round(s.searches_per_listing, 2) if s.searches_per_listing is not None else None,
          round(s.score, 1), s.label, _trend_text(s.row.metrics.trend), _origin(s.row),
          _local_date(s.row.checked_at)] for s in ranked],
        [30, 16, 15, 12, 20, 8, 12, 8, 30, 12], percent_cols=[3])
    for r in range(3, peluang.max_row + 1):
        label_cell = peluang.cell(r, 7)
        color = LABEL_FILLS.get(label_cell.value)
        if color:
            label_cell.fill = PatternFill("solid", fgColor=color)

    labels = {s.row.keyword: s.label for s in scored}
    semua = wb.create_sheet("Semua data")
    _write_table(
        semua, f"Diperbarui {today}. {len(history)} hasil pengecekan.", SEMUA_HEADERS,
        [[r.keyword, r.status, _local_date(r.checked_at), r.metrics.search_volume, r.metrics.conversion_rate,
          _competition(r), _COMPETITION_KIND_TEXT.get(r.metrics.competition_kind or "", ""),
          ", ".join(r.metrics.related), labels.get(r.keyword, "")] for r in history],
        [30, 10, 12, 16, 15, 12, 16, 50, 14], percent_cols=[5])

    antrean = wb.create_sheet("Antrean")
    _write_table(
        antrean, f"Diperbarui {today}. {len(queue)} keyword menunggu.", ANTREAN_HEADERS,
        [[q.keyword, "daftar Anda" if q.source == "user" else "terkait", q.depth, q.parent_keyword or "",
          _local_date(q.added_at)] for q in queue],
        [30, 12, 10, 30, 12])

    wb.save(path)
    return path
