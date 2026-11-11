"""Tipe data bersama yang dipakai semua modul."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

CompetitionKind = Literal["count", "level"]  # level: 1=Rendah, 2=Sedang, 3=Tinggi
CONVERSION_LEVEL_TEXT = {0: "Very low", 1: "Low", 2: "Typical", 3: "High", 4: "Very high"}


@dataclass(frozen=True)
class KeywordMetrics:
    has_data: bool
    search_volume: int | None = None
    conversion_rate: float | None = None  # queryCvr Etsy (pecahan); hanya untuk hasil cari
    competition_value: float | None = None
    competition_kind: CompetitionKind | None = None
    trend: tuple[float, ...] = ()  # terlama -> terbaru
    related: tuple[str, ...] = ()
    conversion_level: int | None = None  # level Etsy 0..4 (Very low..Very high)
    wow_pct: float | None = None  # perubahan minggu-ke-minggu (%)


@dataclass(frozen=True)
class RelatedKeyword:
    keyword: str
    search_volume: int | None
    competition_value: float | None
    conversion_level: int | None


@dataclass(frozen=True)
class EtsyQuota:
    total: int | None
    remaining: int | None
    low_threshold: int | None
    reached: bool
    search_allowed: bool

    @property
    def exhausted(self) -> bool:
        low = (self.remaining is not None and self.low_threshold is not None
               and self.remaining <= self.low_threshold)
        return self.reached or not self.search_allowed or low


@dataclass(frozen=True)
class ParsedSearch:
    main: KeywordMetrics
    related: tuple[RelatedKeyword, ...] = ()
    quota: EtsyQuota | None = None


@dataclass(frozen=True)
class CapturedResponse:
    url: str
    status: int
    body: Any


@dataclass(frozen=True)
class RawResult:
    keyword: str
    page_url: str
    responses: tuple[CapturedResponse, ...]
    html: str


@dataclass(frozen=True)
class DangerSignal:
    kind: Literal["captcha", "verifikasi", "login", "http_403", "http_429"]
    detail: str


@dataclass(frozen=True)
class QueueItem:
    id: int
    keyword: str
    source: Literal["user", "related"]
    depth: int
    parent_keyword: str | None
    status: str
    fail_count: int
    added_at: datetime


@dataclass(frozen=True)
class ResultRow:
    keyword_id: int
    keyword: str
    source: str
    depth: int
    parent_keyword: str | None
    status: str
    checked_at: datetime
    metrics: KeywordMetrics
    kind: str = "search"  # "search" | "panen"


class NotLoggedIn(Exception):
    """Chrome profil Etsy Riset belum login ke Etsy."""


class PageLoadTimeout(Exception):
    """Halaman tidak selesai dimuat dalam batas waktu."""


class BrowserClosed(Exception):
    """Chrome ditutup saat sesi berjalan."""


class ParseError(Exception):
    """Data halaman tidak bisa dibaca."""


class EtsyQuotaReached(Exception):
    """Etsy menandai kuota Marketplace Insights habis (respons tanpa data utama)."""

    def __init__(self, quota: EtsyQuota) -> None:
        super().__init__("Kuota Marketplace Insights habis")
        self.quota = quota


class InsightsPage(Protocol):
    def open(self) -> None: ...  # bisa raise NotLoggedIn

    def search(self, keyword: str) -> RawResult: ...  # bisa raise PageLoadTimeout, BrowserClosed

    def check_danger(self) -> DangerSignal | None: ...

    def dwell(self, seconds: float, scroll: bool) -> None: ...
