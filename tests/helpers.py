"""Data contoh dan objek palsu untuk tes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from etsy_insights.models import KeywordMetrics, RawResult, RelatedKeyword, ResultRow

T0 = datetime(2026, 11, 11, 10, 0, tzinfo=timezone(timedelta(hours=7)))
INSIGHTS = "https://www.etsy.com/your/shops/me/marketplace-insights"


def make_metrics(volume=1000, cr=0.05, comp=100.0, kind="count", related=(), trend=(), has_data=True,
                 level=2, wow=None):
    return KeywordMetrics(has_data=has_data, search_volume=volume, conversion_rate=cr,
                          competition_value=comp, competition_kind=kind,
                          trend=tuple(trend), related=tuple(related), conversion_level=level, wow_pct=wow)


def make_related(keyword, volume=1000, comp=100, level=2):
    return RelatedKeyword(keyword, volume, comp, level)


def make_raw(keyword):
    return RawResult(keyword=keyword, page_url=INSIGHTS, responses=(), html="")


def make_row(keyword, volume, level, comp, kind="count", source="user", parent=None,
             has_data=True, trend=(), keyword_id=0, wow=None, rate=None, row_kind="search"):
    metrics = KeywordMetrics(has_data=has_data, search_volume=volume, conversion_rate=rate,
                             competition_value=comp, competition_kind=kind if comp is not None else None,
                             trend=tuple(trend), conversion_level=level, wow_pct=wow)
    if row_kind == "panen":
        status = "harvested"
    else:
        status = "done" if has_data else "no_data"
    return ResultRow(keyword_id=keyword_id, keyword=keyword, source=source,
                     depth=0 if source == "user" else 1, parent_keyword=parent,
                     status=status, checked_at=T0, metrics=metrics, kind=row_kind)


# --- Fakes untuk tes sesi --------------------------------------------------
import random  # noqa: E402

from etsy_insights.config import Config  # noqa: E402
from etsy_insights.models import (  # noqa: E402
    BrowserClosed, CapturedResponse, DangerSignal, EtsyQuota, PageLoadTimeout, ParsedSearch, ParseError)


class FakeClock:
    def __init__(self, start, interrupt_on_sleep=None):
        self._now = start
        self._interrupt_on_sleep = interrupt_on_sleep
        self.sleeps: list[float] = []

    def now(self):
        return self._now

    def advance(self, seconds):
        self._now += timedelta(seconds=seconds)

    def sleep(self, seconds):
        if self._interrupt_on_sleep is not None and len(self.sleeps) + 1 == self._interrupt_on_sleep:
            raise KeyboardInterrupt
        self.sleeps.append(seconds)
        self.advance(seconds)


class FakePage:
    def __init__(self, clock, outcomes=None, related=None, danger_on_open=None, open_error=None):
        self.clock = clock
        self.outcomes = outcomes or {}
        self.related = related or {}
        self.danger_on_open = danger_on_open
        self.open_error = open_error
        self.opened = 0
        self.searched: list[str] = []
        self.dwells: list[tuple[float, bool]] = []
        self._danger = None

    def open(self):
        self.opened += 1
        if self.open_error:
            raise self.open_error
        self._danger = self.danger_on_open

    def search(self, keyword):
        self.searched.append(keyword)
        outcome = self.outcomes.get(keyword, "ok")
        if outcome == "timeout":
            raise PageLoadTimeout(keyword)
        if outcome == "timeout_captcha":
            self._danger = DangerSignal("captcha", "CAPTCHA menggantikan halaman")
            raise PageLoadTimeout(keyword)
        if outcome == "closed":
            raise BrowserClosed()
        if outcome == "interrupt":
            raise KeyboardInterrupt
        if outcome == "captcha":
            self._danger = DangerSignal("captcha", "iframe captcha")
        if outcome == "403":
            self._danger = DangerSignal("http_403", "HTTP 403")
        body = {"outcome": outcome, "related": list(self.related.get(keyword, ()))}
        return RawResult(keyword, INSIGHTS, (CapturedResponse("https://www.etsy.com/x", 200, body),), "")

    def check_danger(self):
        if self.searched and self.outcomes.get(self.searched[-1]) == "closed_on_check":
            raise BrowserClosed()
        return self._danger

    def dwell(self, seconds, scroll):
        self.dwells.append((seconds, scroll))
        self.clock.advance(seconds)


def fake_parse(raw):
    body = raw.responses[0].body
    outcome = body["outcome"]
    if outcome == "parse_error":
        raise ParseError("tidak terbaca")
    if outcome == "parse_crash":
        return {}["field_hilang"]
    related = tuple(RelatedKeyword(*t) for t in body["related"])
    main = KeywordMetrics(has_data=False) if outcome == "no_data" else \
        make_metrics(related=[r.keyword for r in related])
    quota = EtsyQuota(15, 5 if outcome == "quota" else 15, 5, False, True)
    return ParsedSearch(main=main, related=related, quota=quota)


def make_deps(store, page, clock, cfg=None, seed=1):
    from etsy_insights.pacer import Pacer
    from etsy_insights.session import SessionDeps
    cfg = cfg or Config()
    return SessionDeps(store=store, page=page, parse=fake_parse, pacer=Pacer(cfg, random.Random(seed)),
                       cfg=cfg, clock=clock.now, sleep=clock.sleep, log=lambda msg: None,
                       parser_version="test")
