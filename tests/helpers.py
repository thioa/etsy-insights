"""Data contoh dan objek palsu untuk tes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from etsy_insights.models import KeywordMetrics, RawResult, ResultRow

T0 = datetime(2026, 11, 11, 10, 0, tzinfo=timezone(timedelta(hours=7)))
INSIGHTS = "https://www.etsy.com/your/shops/me/marketplace-insights"


def make_metrics(volume=1000, cr=0.05, comp=100.0, kind="count", related=(), trend=(), has_data=True):
    return KeywordMetrics(has_data=has_data, search_volume=volume, conversion_rate=cr,
                          competition_value=comp, competition_kind=kind,
                          trend=tuple(trend), related=tuple(related))


def make_raw(keyword):
    return RawResult(keyword=keyword, page_url=INSIGHTS, responses=(), html="")


def make_row(keyword, volume, cr, comp, kind="count", source="user", parent=None,
             has_data=True, trend=(), keyword_id=0):
    metrics = KeywordMetrics(has_data=has_data, search_volume=volume, conversion_rate=cr,
                             competition_value=comp, competition_kind=kind if comp is not None else None,
                             trend=tuple(trend))
    return ResultRow(keyword_id=keyword_id, keyword=keyword, source=source,
                     depth=0 if source == "user" else 1, parent_keyword=parent,
                     status="done" if has_data else "no_data", checked_at=T0, metrics=metrics)
