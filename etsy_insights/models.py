"""Tipe data bersama yang dipakai semua modul."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

CompetitionKind = Literal["count", "level"]  # level: 1=Rendah, 2=Sedang, 3=Tinggi


@dataclass(frozen=True)
class KeywordMetrics:
    has_data: bool
    search_volume: int | None = None
    conversion_rate: float | None = None  # pecahan 0..1
    competition_value: float | None = None
    competition_kind: CompetitionKind | None = None
    trend: tuple[float, ...] = ()  # terlama -> terbaru
    related: tuple[str, ...] = ()


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


class NotLoggedIn(Exception):
    """Chrome profil Etsy Riset belum login ke Etsy."""


class PageLoadTimeout(Exception):
    """Halaman tidak selesai dimuat dalam batas waktu."""


class BrowserClosed(Exception):
    """Chrome ditutup saat sesi berjalan."""


class ParseError(Exception):
    """Data halaman tidak bisa dibaca."""


class InsightsPage(Protocol):
    def open(self) -> None: ...  # bisa raise NotLoggedIn

    def search(self, keyword: str) -> RawResult: ...  # bisa raise PageLoadTimeout, BrowserClosed

    def check_danger(self) -> DangerSignal | None: ...

    def dwell(self, seconds: float, scroll: bool) -> None: ...
