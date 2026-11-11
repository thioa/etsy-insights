"""Menulis hasil ke file Excel."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import CONVERSION_LEVEL_TEXT, QueueItem, ResultRow
from .score import LEVEL_LABELS, ScoredKeyword
from .taste import TasteProfile

PELUANG_HEADERS = ["Keyword", "Volume pencarian", "Pesaing (listing)", "Konversi", "Rasio konversi",
                   "Pencarian per listing", "Skor", "Label", "Tren mingguan", "Asal keyword", "Tanggal data",
                   "Harga pasar", "Kesulitan masuk"]
SELERA_HEADERS = ["Keyword", "Skor", "Label", "Harga dibayar pembeli", "Harga listing teratas", "Kesulitan masuk",
                  "Median ulasan teratas", "% Bestseller", "% Star Seller", "Toko berbeda", "Tema populer",
                  "Contoh 1", "Contoh 2", "Contoh 3", "Contoh 4", "Contoh 5"]
SEMUA_HEADERS = ["Keyword", "Jenis data", "Status", "Tanggal data", "Volume pencarian", "Pesaing (listing)",
                 "Konversi", "Rasio konversi", "Tren mingguan", "Label terbaru"]
ANTREAN_HEADERS = ["Urutan", "Keyword", "Sumber", "Kedalaman", "Asal keyword"]
STATUS_TEXT = {"pending": "menunggu", "in_progress": "sedang dicek", "done": "sudah dicari",
               "no_data": "tanpa data", "failed": "gagal", "harvested": "hasil panen"}
LABEL_FILLS = {"Emas": "FFD966", "Potensial": "C6EFCE", "Lewati": "D9D9D9"}

_FEW_DATA = 10
_RATE_FORMAT = "0.000%"
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_LABEL_COLUMN = PELUANG_HEADERS.index("Label") + 1


def _local_date(dt: datetime) -> str:
    return dt.astimezone().date().isoformat()


def _competition(row: ResultRow):
    m = row.metrics
    if m.competition_value is None:
        return None
    if m.competition_kind == "level":
        return LEVEL_LABELS.get(int(m.competition_value), m.competition_value)
    return m.competition_value


def _level_text(row: ResultRow) -> str:
    level = row.metrics.conversion_level
    return CONVERSION_LEVEL_TEXT.get(level, "") if isinstance(level, int) else ""


def _wow_text(row: ResultRow) -> str:
    wow = row.metrics.wow_pct
    return f"{wow:+.1f}%" if wow is not None else ""


def _origin(row: ResultRow) -> str:
    if row.source == "user":
        return "daftar Anda"
    if row.kind == "panen":
        return f"panen dari: {row.parent_keyword}"
    return f"dicari (asal: {row.parent_keyword})"


def _range(low: str | None, high: str | None) -> str:
    return f"{low} – {high}" if low and high else ""


def _selera_rows(scored: Sequence[ScoredKeyword], profiles: Mapping[str, TasteProfile]) -> list[tuple]:
    """(profil, skor) dalam urutan sheet Peluang; profil tanpa baris skor ditaruh paling akhir."""
    ordered = [s for s in scored if s.eligible] + sorted((s for s in scored if not s.eligible),
                                                         key=lambda s: s.row.keyword)
    rows = [(profiles[s.row.keyword], s) for s in ordered if s.row.keyword in profiles]
    seen = {s.row.keyword for s in ordered}
    rows += [(profiles[k], None) for k in sorted(profiles) if k not in seen]
    return rows


def _example_text(card) -> str:
    reviews = card.reviews if card.reviews is not None else "?"
    return f"{card.title[:80]} | {card.price_text} | {reviews} ulasan"


def _write_table(ws: Worksheet, info: str, headers: list[str], rows: list[list],
                 widths: list[int], formats: dict[int, str] | None = None) -> None:
    ws["A1"] = info
    ws["A1"].font = Font(italic=True)
    ws.append(headers)
    for cell in ws[2]:
        cell.font = Font(bold=True)
    for values in rows:
        ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in values])
    for r in range(3, ws.max_row + 1):
        for cell in ws[r]:
            if isinstance(cell.value, str) and cell.value.startswith(_FORMULA_PREFIXES):
                cell.data_type = "s"  # teks, bukan rumus
        for col, number_format in (formats or {}).items():
            ws.cell(r, col).number_format = number_format
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}{max(2, ws.max_row)}"
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def export_excel(scored: Sequence[ScoredKeyword], history: Sequence[ResultRow],
                 queue: Sequence[QueueItem], out_dir: Path, today: date,
                 profiles: Mapping[str, TasteProfile] | None = None) -> Path:
    profiles = profiles or {}
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
        [[s.row.keyword, s.row.metrics.search_volume, _competition(s.row), _level_text(s.row),
          s.row.metrics.conversion_rate,
          round(s.searches_per_listing, 4) if s.searches_per_listing is not None else None,
          round(s.score, 1), s.label, _wow_text(s.row), _origin(s.row), _local_date(s.row.checked_at),
          _range(profiles[s.row.keyword].paid_price_low, profiles[s.row.keyword].paid_price_high)
          if s.row.keyword in profiles else "",
          profiles[s.row.keyword].difficulty if s.row.keyword in profiles else ""]
         for s in ranked],
        [30, 16, 17, 14, 14, 20, 8, 12, 14, 30, 12, 22, 16], formats={5: _RATE_FORMAT})
    for r in range(3, peluang.max_row + 1):
        label_cell = peluang.cell(r, _LABEL_COLUMN)
        color = LABEL_FILLS.get(label_cell.value)
        if color:
            label_cell.fill = PatternFill("solid", fgColor=color)

    selera = wb.create_sheet("Selera")
    selera_rows = _selera_rows(scored, profiles)
    _write_table(
        selera, f"Profil selera untuk {len(selera_rows)} keyword yang sudah dicari "
                "(±20 listing teratas di Marketplace Insights).", SELERA_HEADERS,
        [[p.keyword, round(s.score, 1) if s is not None and s.score is not None else None,
          s.label if s is not None else "", _range(p.paid_price_low, p.paid_price_high),
          _range(p.listing_price_low, p.listing_price_high), p.difficulty, p.median_reviews,
          p.bestseller_share, p.star_seller_share, p.unique_shops,
          ", ".join(f"{term} ({n})" for term, n in p.top_terms),
          *[_example_text(card) for card in p.examples]] for p, s in selera_rows],
        [26, 8, 12, 22, 26, 14, 12, 12, 12, 12, 60, 50, 50, 50, 50, 50], formats={8: "0%", 9: "0%"})
    first_example = SELERA_HEADERS.index("Contoh 1") + 1
    for r, (profile, _) in enumerate(selera_rows, start=3):
        for i, card in enumerate(profile.examples):
            if card.url:
                selera.cell(r, first_example + i).hyperlink = card.url

    labels = {s.row.keyword: s.label for s in scored}
    semua = wb.create_sheet("Semua data")
    _write_table(
        semua, f"Diperbarui {today}. {len(history)} baris data.", SEMUA_HEADERS,
        [[r.keyword, "panen" if r.kind == "panen" else "dicari", STATUS_TEXT.get(r.status, r.status),
          _local_date(r.checked_at), r.metrics.search_volume, _competition(r), _level_text(r),
          r.metrics.conversion_rate, _wow_text(r), labels.get(r.keyword, "")] for r in history],
        [30, 10, 14, 12, 16, 17, 14, 14, 14, 14], formats={8: _RATE_FORMAT})

    antrean = wb.create_sheet("Antrean")
    _write_table(
        antrean, f"Diperbarui {today}. {len(queue)} keyword berikutnya yang akan dicari.", ANTREAN_HEADERS,
        [[i, q.keyword, "daftar Anda" if q.source == "user" else "hasil panen", q.depth, q.parent_keyword or ""]
         for i, q in enumerate(queue, start=1)],
        [8, 30, 14, 10, 30])

    wb.save(path)
    return path
