"""Laporan AI Advisor di etsy.db (spec Tahap 6 §8)."""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Store

ADVISOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS advisor_reports (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    model TEXT,
    error TEXT,
    trend_note TEXT,
    trend_failed INTEGER NOT NULL DEFAULT 0,
    sources_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT,
    stats_json TEXT NOT NULL DEFAULT '{}',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    web_searches INTEGER NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Source:
    id: str  # "S1", "S2", …
    url: str
    title: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    web_searches: int = 0
    cost_cents: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(Usage)))


@dataclass(frozen=True)
class Report:
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str  # running | done | error | interrupted
    stage: str | None
    model: str | None
    error: str | None
    trend_note: str | None
    trend_failed: bool
    sources: tuple[Source, ...]
    result: dict | None
    stats: dict
    usage: Usage


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _dt(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _sources_json(sources: Sequence[Source]) -> str:
    return json.dumps([{"id": s.id, "url": s.url, "title": s.title} for s in sources])


class AdvisorStore:
    def __init__(self, store: Store) -> None:
        self._db = store.connection

    def start_report(self, now: datetime, model: str) -> int:
        cursor = self._db.execute("INSERT INTO advisor_reports (started_at, status, model) VALUES (?, 'running', ?)",
                                  (_ts(now), model))
        return int(cursor.lastrowid)

    def set_stage(self, report_id: int, stage: str) -> None:
        self._db.execute("UPDATE advisor_reports SET stage = ? WHERE id = ?", (stage, report_id))

    def _close(self, report_id: int, now: datetime, status: str, error: str | None, trend_note: str | None,
               trend_failed: bool, sources: Sequence[Source], result: dict | None, stats: dict | None,
               usage: Usage) -> None:
        self._db.execute(
            "UPDATE advisor_reports SET finished_at = ?, status = ?, stage = NULL, error = ?, trend_note = ?, "
            "trend_failed = ?, sources_json = ?, result_json = ?, stats_json = COALESCE(?, stats_json), "
            "input_tokens = ?, output_tokens = ?, web_searches = ?, cost_cents = ? WHERE id = ?",
            (_ts(now), status, error, trend_note, int(trend_failed), _sources_json(sources),
             json.dumps(result) if result is not None else None, json.dumps(stats) if stats is not None else None,
             usage.input_tokens, usage.output_tokens, usage.web_searches, usage.cost_cents, report_id))

    def finish_report(self, report_id: int, now: datetime, *, trend_note: str | None, trend_failed: bool,
                      sources: Sequence[Source], result: dict, stats: dict, usage: Usage,
                      model: str | None = None) -> None:
        """`model`: model yang benar-benar menulis analisis (bisa model fallback)."""
        self._close(report_id, now, "done", None, trend_note, trend_failed, sources, result, stats, usage)
        if model:
            self._db.execute("UPDATE advisor_reports SET model = ? WHERE id = ?", (model, report_id))

    def fail_report(self, report_id: int, now: datetime, error: str, usage: Usage, *, trend_note: str | None = None,
                    trend_failed: bool = False, sources: Sequence[Source] = ()) -> None:
        self._close(report_id, now, "error", error, trend_note, trend_failed, sources, None, None, usage)

    def mark_interrupted(self) -> int:
        cursor = self._db.execute("UPDATE advisor_reports SET status = 'interrupted', stage = NULL "
                                  "WHERE status = 'running'")
        return cursor.rowcount

    @staticmethod
    def _report(row) -> Report:
        return Report(
            id=row["id"], started_at=_dt(row["started_at"]), finished_at=_dt(row["finished_at"]),
            status=row["status"], stage=row["stage"], model=row["model"], error=row["error"],
            trend_note=row["trend_note"], trend_failed=bool(row["trend_failed"]),
            sources=tuple(Source(s["id"], s["url"], s["title"]) for s in json.loads(row["sources_json"] or "[]")),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            stats=json.loads(row["stats_json"] or "{}"),
            usage=Usage(row["input_tokens"], row["output_tokens"], row["web_searches"], row["cost_cents"]))

    def report(self, report_id: int) -> Report | None:
        row = self._db.execute("SELECT * FROM advisor_reports WHERE id = ?", (report_id,)).fetchone()
        return self._report(row) if row is not None else None

    def reports(self, limit: int = 20) -> list[Report]:
        rows = self._db.execute("SELECT * FROM advisor_reports ORDER BY started_at DESC, id DESC LIMIT ?",
                                (limit,)).fetchall()
        return [self._report(r) for r in rows]

    def month_spend(self, now: datetime) -> tuple[int, int]:
        """(jumlah laporan, total sen) di bulan kalender lokal `now`, semua status."""
        runs = cents = 0
        for started, cost in self._db.execute("SELECT started_at, cost_cents FROM advisor_reports"):
            local = _dt(started).astimezone(now.tzinfo)
            if (local.year, local.month) == (now.year, now.month):
                runs += 1
                cents += cost
        return runs, cents
