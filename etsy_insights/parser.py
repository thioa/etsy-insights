"""Membaca respons Marketplace Insights menjadi data keyword utama + keyword terkait (spec §16.1)."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qs, urlparse

from .models import (CapturedResponse, EtsyQuota, EtsyQuotaReached, KeywordMetrics, ParsedSearch, ParseError,
                     RawResult, RelatedKeyword)
from .store import normalize_keyword

PARSER_VERSION = "1"
RESULTS_PATH = "/marketplace-insights/results-data"
POLL_PATH = "/llm-exploratory-keywords/search/poll"
ENQUEUE_PATH = "/llm-exploratory-keywords/search/enqueue"


def _path(url: str) -> str:
    return urlparse(url).path


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _is_results_response(resp: CapturedResponse, keyword: str) -> bool:
    if not _path(resp.url).endswith(RESULTS_PATH) or resp.status != 200 or not isinstance(resp.body, dict):
        return False
    query = parse_qs(urlparse(resp.url).query).get("query", [""])[0]
    return normalize_keyword(query) == normalize_keyword(keyword)


def is_results_for(resp: CapturedResponse, keyword: str) -> bool:
    return _is_results_response(resp, keyword) and isinstance(resp.body.get("stats"), dict)


def blocked_quota(responses: Sequence[CapturedResponse], keyword: str) -> EtsyQuota | None:
    """Kuota habis yang dilaporkan Etsy di respons results-data tanpa data utama."""
    for resp in reversed(responses):
        if _is_results_response(resp, keyword) and not isinstance(resp.body.get("stats"), dict):
            quota = _quota(resp.body)
            if quota is not None and quota.exhausted:
                return quota
    return None


def related_rows_for(responses: Sequence[CapturedResponse], keyword: str) -> list[dict] | None:
    """Daftar keyword terkait untuk keyword ini. Poll milik keyword lain (basi) tidak pernah dipakai."""
    wanted = normalize_keyword(keyword)
    for resp in reversed(responses):
        body = resp.body
        if (_path(resp.url).endswith(POLL_PATH) and isinstance(body, dict) and body.get("status") == "success"
                and normalize_keyword(str(body.get("inputKeyword") or "")) == wanted
                and isinstance(body.get("results"), list)):
            return body["results"]
    for resp in reversed(responses):
        body = resp.body
        if _path(resp.url).endswith(ENQUEUE_PATH) and isinstance(body, dict):
            cached = body.get("cachedData")
            if isinstance(cached, dict) and isinstance(cached.get("results"), list):
                return cached["results"]
    return None


def _related(rows: list[dict] | None) -> tuple[RelatedKeyword, ...]:
    related = []
    for row in rows or []:
        if not isinstance(row, dict) or not isinstance(row.get("searchTerm"), str):
            continue
        related.append(RelatedKeyword(row["searchTerm"], _int(row.get("searchVolume")),
                                      _number(row.get("avgTotalListings")), _int(row.get("cvr"))))
    return tuple(related)


def _quota(body: dict) -> EtsyQuota | None:
    data = body.get("quotaData")
    if not isinstance(data, dict) and "isQuotaReached" not in body and "isSearchAllowed" not in body:
        return None
    data = data if isinstance(data, dict) else {}
    return EtsyQuota(_int(data.get("totalQuota")), _int(data.get("remainingQuota")),
                     _int(data.get("lowRemainingQuotaThreshold")), bool(body.get("isQuotaReached")),
                     body.get("isSearchAllowed") is not False)


def parse_search(raw: RawResult) -> ParsedSearch:
    results = [r for r in raw.responses if is_results_for(r, raw.keyword)]
    if not results:
        quota = blocked_quota(raw.responses, raw.keyword)
        if quota is not None:
            raise EtsyQuotaReached(quota)
        raise ParseError(f"Main data for '{raw.keyword}' not found.")
    body = results[-1].body
    stats = body["stats"]
    daily = (body.get("dailyStats") or {}).get("stats") if isinstance(body.get("dailyStats"), dict) else None
    trend = tuple(v for v in (_number(d.get("searchVolume")) for d in daily or [] if isinstance(d, dict))
                  if v is not None)
    wow = body.get("wowData") if isinstance(body.get("wowData"), dict) else {}
    volume = _int(stats.get("searchVolume"))
    listings = _number(stats.get("avgTotalListings"))
    related = _related(related_rows_for(raw.responses, raw.keyword))
    main = KeywordMetrics(
        has_data=bool(volume), search_volume=volume, conversion_rate=_number(stats.get("queryCvr")),
        competition_value=listings, competition_kind="count" if listings is not None else None,
        trend=trend, related=tuple(r.keyword for r in related),
        conversion_level=_int(stats.get("cvr")), wow_pct=_number(wow.get("value")))
    return ParsedSearch(main=main, related=related, quota=_quota(body))
