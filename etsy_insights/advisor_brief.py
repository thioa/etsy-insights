"""Ringkasan data untuk AI Advisor (spec Tahap 6 §6.1–§6.2). Fungsi murni di atas database; tidak ada jaringan.

Yang tidak pernah masuk ke sini: token Printify, API key, login Etsy, nama toko, URL listing, contoh listing.
"""
from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from .catalog import OTHER, CategoryIndex, categories_from, summarize
from .config import Config
from .models import CONVERSION_LEVEL_TEXT
from .pacer import remaining_quota
from .printify_store import PrintifyStore
from .product_fit import fits_for_store
from .product_words import category_for
from .score import ScoredKeyword, score_all
from .store import Store
from .taste import TasteProfile, build_profiles

TAKEN_STATUSES = ("pending", "in_progress", "done", "no_data")
MARKET = "Etsy buyers in the United States; free shipping"
MAX_KEYWORDS = 200
MAX_RISING = 60
RISING_PCT = 20.0
TOP_FOR_TRENDS = 20
MAX_EXISTING = 3000


@dataclass(frozen=True)
class TrendInput:
    today: date
    categories: tuple[str, ...]  # nama tampilan, tanpa Other
    top_keywords: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisInput:
    payload: dict
    category_keys: tuple[str, ...]
    keyword_count: int
    category_count: int


def trend_pct(trend: Sequence[float]) -> float | None:
    """Rata-rata 7 hari terakhir dibanding rata-rata semua hari sebelumnya (%)."""
    if len(trend) < 14:
        return None
    earlier = statistics.fmean(trend[:-7])
    if earlier <= 0:
        return None
    return round((statistics.fmean(trend[-7:]) - earlier) / earlier * 100, 1)


def select_keywords(scored: Sequence[ScoredKeyword], cfg: Config, limit: int = MAX_KEYWORDS,
                    rising_limit: int = MAX_RISING) -> list[ScoredKeyword]:
    """Keyword yang naik dulu, lalu skor tertinggi, lalu volume tertinggi (spec §6.2)."""
    rising = []
    for item in scored:
        volume = item.row.metrics.search_volume
        change = trend_pct(item.row.metrics.trend)
        if volume is not None and volume >= cfg.volume_minimum and change is not None and change >= RISING_PCT:
            rising.append((change, item))
    rising.sort(key=lambda pair: (-pair[0], pair[1].row.keyword))
    eligible = sorted((s for s in scored if s.eligible), key=lambda s: (-s.score, s.row.keyword))
    by_volume = sorted((s for s in scored if s.row.metrics.search_volume is not None),
                       key=lambda s: (-s.row.metrics.search_volume, s.row.keyword))
    chosen: dict[str, ScoredKeyword] = {}
    for group, cap in (([s for _, s in rising], rising_limit), (eligible, limit), (by_volume, limit)):
        added = 0
        for item in group:
            if len(chosen) >= limit or added >= cap:
                break
            if item.row.keyword not in chosen:
                chosen[item.row.keyword] = item
                added += 1
    return list(chosen.values())


def _usd(cents: int | None) -> str | None:
    return f"{cents / 100:.2f}" if cents is not None else None


def _buyers(profile: TasteProfile) -> dict:
    paid = (f"{profile.paid_price_low}–{profile.paid_price_high}"
            if profile.paid_price_low and profile.paid_price_high else None)
    return {"paid_price": paid, "difficulty": profile.difficulty,
            "top_words": [term for term, _ in profile.top_terms[:5]], "median_reviews": profile.median_reviews,
            "bestseller_share": round(profile.bestseller_share, 2)}


def _keyword(item: ScoredKeyword, category: str | None, fit, profile: TasteProfile | None) -> dict:
    metrics = item.row.metrics
    entry = {
        "keyword": item.row.keyword, "category": category, "volume": metrics.search_volume,
        "conversion": CONVERSION_LEVEL_TEXT.get(metrics.conversion_level) if metrics.conversion_level is not None
        else None,
        "competition": metrics.competition_value,
        "searches_per_listing": round(item.searches_per_listing, 2) if item.searches_per_listing is not None else None,
        "score": round(item.score, 1) if item.score is not None else None, "label": item.label,
        "trend_pct": trend_pct(metrics.trend),
        "week_change_pct": round(metrics.wow_pct, 1) if metrics.wow_pct is not None else None,
        "margin_usd": _usd(fit.margin.margin_cents) if fit is not None and fit.margin.status == "ok" else None,
        "ready_to_sell": fit.ready if fit is not None else None,
    }
    if profile is not None:
        entry["buyers"] = _buyers(profile)
    return entry


def build_inputs(store: Store, cfg: Config, now: datetime) -> tuple[TrendInput, AnalysisInput]:
    printify = PrintifyStore(store)
    categories = categories_from(printify.blueprints())
    scored = score_all(store.latest_results(), cfg)
    summaries = summarize(store, cfg, categories, scored)
    mains = sorted((m for m in categories if m != OTHER), key=lambda m: categories[m].name.lower())

    costs: dict[str, list[int]] = {}
    for item in printify.types(include_unavailable=False):
        if item.cost_min_cents is not None:
            costs.setdefault(category_for(item.title), []).extend(
                c for c in (item.cost_min_cents, item.cost_max_cents) if c is not None)

    category_rows = []
    for main in mains:
        summary = summaries[main]
        cost = costs.get(main)
        category_rows.append({
            "key": main, "name": summary.info.name, "models": summary.models,
            "in_my_products": summary.in_my_products,
            "production_cost_usd": f"{_usd(min(cost))}–{_usd(max(cost))}" if cost else None,
            "keywords_with_data": summary.keywords, "gold": summary.gold, "potential": summary.potential,
            "most_searched": ({"keyword": summary.most_searched[0], "volume": summary.most_searched[1]}
                              if summary.most_searched else None),
            "ready_to_sell": summary.ready, "research": summary.research.status,
        })

    selected = select_keywords(scored, cfg)
    index = CategoryIndex(mains)
    profiles = build_profiles(store, only=[s.row.keyword for s in selected])
    fits = fits_for_store(store, cfg, [s for s in selected if s.row.keyword in profiles], profiles)
    keyword_rows = []
    for item in selected:
        found = sorted(index.categories(item.row.keyword))
        keyword_rows.append(_keyword(item, found[0] if found else None, fits.get(item.row.keyword),
                                     profiles.get(item.row.keyword)))

    counts = store.status_counts()
    today = now.date()
    payload = {
        "context": {
            "today": today.isoformat(), "market": MARKET, "daily_searches": cfg.kuota_harian,
            "searches_left_today": remaining_quota(cfg, store.checked_on(today, now.tzinfo)),
            "in_queue": counts.get("pending", 0) + counts.get("in_progress", 0),
            "etsy_fee_percent": cfg.fee_etsy_persen, "etsy_fixed_fee_usd": cfg.fee_etsy_tetap_usd,
            "minimum_margin_usd": cfg.margin_minimum_usd,
        },
        "categories": category_rows,
        "keywords": keyword_rows,
        "existing_keywords": store.searched_or_queued(MAX_EXISTING),
    }
    top = tuple(s.row.keyword for s in sorted((s for s in scored if s.eligible),
                                                key=lambda s: (-s.score, s.row.keyword))[:TOP_FOR_TRENDS])
    trend_input = TrendInput(today, tuple(categories[m].name for m in mains), top)
    analysis = AnalysisInput(payload, tuple(mains), len(keyword_rows), len(category_rows))
    return trend_input, analysis
