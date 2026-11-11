"""Skor peluang 0-100 berbasis persentil, plus label Emas/Potensial/Lewati."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .config import Config
from .models import ResultRow

EMAS_THRESHOLD = 200 / 3  # sepertiga teratas
POTENSIAL_THRESHOLD = 60.0
LEVEL_LABELS = {1: "Rendah", 2: "Sedang", 3: "Tinggi"}


@dataclass(frozen=True)
class ScoredKeyword:
    row: ResultRow
    eligible: bool
    p_volume: float | None
    p_conversion: float | None
    p_low_competition: float | None
    score: float | None
    label: str  # "Emas" | "Potensial" | "Lewati" | "Data kurang"
    searches_per_listing: float | None


def percentile_ranks(values: Sequence[float]) -> list[float]:
    """Persentil 0-100; nilai seri mendapat rank rata-rata; satu nilai -> 50."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [50.0]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return [(100 * (r - 1)) / (n - 1) for r in ranks]


def label_for(p_volume: float | None, p_conversion: float | None,
              p_low_competition: float | None, score: float) -> str:
    present = [p for p in (p_volume, p_conversion, p_low_competition) if p is not None]
    if present and all(p >= EMAS_THRESHOLD for p in present):
        return "Emas"
    if score >= POTENSIAL_THRESHOLD:
        return "Potensial"
    return "Lewati"


def _searches_per_listing(row: ResultRow) -> float | None:
    m = row.metrics
    if m.competition_kind == "count" and m.search_volume is not None and m.competition_value:
        return m.search_volume / m.competition_value
    return None


def score_all(rows: Sequence[ResultRow], cfg: Config) -> list[ScoredKeyword]:
    with_data = [r for r in rows if r.metrics.has_data]
    getters = {
        "volume": lambda r: r.metrics.search_volume,
        "conversion": lambda r: r.metrics.conversion_level,
        "competition": lambda r: r.metrics.competition_value,
    }
    available = [name for name, get in getters.items() if any(get(r) is not None for r in with_data)]

    def is_eligible(r: ResultRow) -> bool:
        m = r.metrics
        return (m.has_data and m.search_volume is not None and m.search_volume >= cfg.volume_minimum
                and all(getters[name](r) is not None for name in available))

    eligible = [r for r in rows if is_eligible(r)]
    percentiles: dict[str, list[float]] = {
        name: percentile_ranks([getters[name](r) for r in eligible]) for name in available}
    if "competition" in percentiles:
        percentiles["competition"] = [100 - p for p in percentiles["competition"]]

    weight_by_name = dict(zip(("volume", "conversion", "competition"), cfg.bobot))
    total_weight = sum(weight_by_name[name] for name in available) or 1.0

    scored: list[ScoredKeyword] = []
    for idx, row in enumerate(eligible):
        p = {name: percentiles[name][idx] for name in available}
        score = sum(weight_by_name[name] / total_weight * p[name] for name in available)
        pv, pc, pk = p.get("volume"), p.get("conversion"), p.get("competition")
        scored.append(ScoredKeyword(row, True, pv, pc, pk, score, label_for(pv, pc, pk, score),
                                    _searches_per_listing(row)))
    scored.sort(key=lambda s: (-s.score, s.row.keyword))

    eligible_ids = {id(r) for r in eligible}
    rest = sorted((r for r in rows if id(r) not in eligible_ids), key=lambda r: r.keyword)
    scored.extend(ScoredKeyword(r, False, None, None, None, None, "Data kurang", _searches_per_listing(r))
                  for r in rest)
    return scored
