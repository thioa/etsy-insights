"""Database SQLite lokal: antrean keyword, hasil, dan sesi."""
from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from collections.abc import Collection, Iterable
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

from .models import KeywordMetrics, QueueItem, RawResult, ResultRow

MAX_FAILURES = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY,
    keyword TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    parent_id INTEGER REFERENCES keywords(id),
    depth INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    added_at TEXT NOT NULL,
    last_checked_at TEXT,
    fail_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    checked_at TEXT NOT NULL,
    has_data INTEGER NOT NULL,
    search_volume INTEGER,
    conversion_rate REAL,
    competition_value REAL,
    competition_kind TEXT,
    trend_json TEXT,
    related_json TEXT,
    raw_json TEXT,
    parser_version TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    checked_count INTEGER NOT NULL DEFAULT 0,
    stop_reason TEXT,
    cooldown_until TEXT
);
"""

_KEYWORD_COLUMNS = """
    k.id, k.keyword, k.source, k.depth, p.keyword AS parent_keyword,
    k.status, k.fail_count, k.added_at
"""
_QUEUE_ORDER = "CASE k.source WHEN 'user' THEN 0 ELSE 1 END, k.depth, k.added_at, k.id"


def normalize_keyword(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def read_keywords_file(path: Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    seen: dict[str, None] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("#"):
            continue
        keyword = normalize_keyword(line)
        if keyword:
            seen.setdefault(keyword, None)
    return list(seen)


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _dt(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


class Store:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # --- keyword & antrean -------------------------------------------------
    def _queue_item(self, row: sqlite3.Row) -> QueueItem:
        return QueueItem(id=row["id"], keyword=row["keyword"], source=row["source"], depth=row["depth"],
                         parent_keyword=row["parent_keyword"], status=row["status"],
                         fail_count=row["fail_count"], added_at=_dt(row["added_at"]))

    def get(self, keyword: str) -> QueueItem | None:
        row = self._db.execute(
            f"SELECT {_KEYWORD_COLUMNS} FROM keywords k LEFT JOIN keywords p ON k.parent_id = p.id "
            "WHERE k.keyword = ?", (normalize_keyword(keyword),)).fetchone()
        return self._queue_item(row) if row else None

    def sync_user_keywords(self, keywords: Iterable[str], now: datetime) -> int:
        changed = 0
        for keyword in dict.fromkeys(normalize_keyword(k) for k in keywords):
            if not keyword:
                continue
            existing = self.get(keyword)
            if existing is None:
                self._db.execute(
                    "INSERT INTO keywords (keyword, source, parent_id, depth, added_at) VALUES (?, 'user', NULL, 0, ?)",
                    (keyword, _ts(now)))
                changed += 1
            elif existing.source != "user":
                self._db.execute(
                    "UPDATE keywords SET source = 'user', parent_id = NULL, depth = 0 WHERE id = ?", (existing.id,))
                changed += 1
        return changed

    def add_related(self, parent_id: int, keywords: Iterable[str], max_count: int, max_depth: int,
                    now: datetime) -> int:
        parent = self._db.execute("SELECT depth FROM keywords WHERE id = ?", (parent_id,)).fetchone()
        if parent is None or parent["depth"] + 1 > max_depth:
            return 0
        added = 0
        for keyword in dict.fromkeys(normalize_keyword(k) for k in keywords):
            if added >= max_count:
                break
            if not keyword or self.get(keyword) is not None:
                continue
            self._db.execute(
                "INSERT INTO keywords (keyword, source, parent_id, depth, added_at) VALUES (?, 'related', ?, ?, ?)",
                (keyword, parent_id, parent["depth"] + 1, _ts(now)))
            added += 1
        return added

    def next_keyword(self, now: datetime, recheck_days: int,
                     exclude_ids: Collection[int] = ()) -> QueueItem | None:
        exclude = list(exclude_ids)
        not_in = f"AND k.id NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        base = f"SELECT {_KEYWORD_COLUMNS} FROM keywords k LEFT JOIN keywords p ON k.parent_id = p.id"
        row = self._db.execute(
            f"{base} WHERE k.status = 'pending' {not_in} ORDER BY {_QUEUE_ORDER} LIMIT 1", exclude).fetchone()
        if row is None:
            cutoff = _ts(now - timedelta(days=recheck_days))
            row = self._db.execute(
                f"{base} WHERE k.status IN ('done', 'no_data') AND k.last_checked_at < ? {not_in} "
                "ORDER BY k.last_checked_at, k.id LIMIT 1", [cutoff, *exclude]).fetchone()
        return self._queue_item(row) if row else None

    def pending_queue(self) -> list[QueueItem]:
        rows = self._db.execute(
            f"SELECT {_KEYWORD_COLUMNS} FROM keywords k LEFT JOIN keywords p ON k.parent_id = p.id "
            f"WHERE k.status = 'pending' ORDER BY {_QUEUE_ORDER}").fetchall()
        return [self._queue_item(r) for r in rows]

    def mark_in_progress(self, keyword_id: int) -> None:
        self._db.execute("UPDATE keywords SET status = 'in_progress' WHERE id = ?", (keyword_id,))

    def return_to_pending(self, keyword_id: int) -> None:
        self._db.execute("UPDATE keywords SET status = 'pending' WHERE id = ?", (keyword_id,))

    def recover_in_progress(self) -> int:
        return self._db.execute("UPDATE keywords SET status = 'pending' WHERE status = 'in_progress'").rowcount

    def record_failure(self, keyword_id: int) -> str:
        self._db.execute("UPDATE keywords SET fail_count = fail_count + 1 WHERE id = ?", (keyword_id,))
        fails = self._db.execute("SELECT fail_count FROM keywords WHERE id = ?", (keyword_id,)).fetchone()[0]
        status = "failed" if fails >= MAX_FAILURES else "pending"
        self._db.execute("UPDATE keywords SET status = ? WHERE id = ?", (status, keyword_id))
        return status

    def status_counts(self) -> dict[str, int]:
        rows = self._db.execute("SELECT status, COUNT(*) FROM keywords GROUP BY status").fetchall()
        return {status: count for status, count in rows if count > 0}

    # --- hasil -------------------------------------------------------------
    def save_result(self, keyword_id: int, metrics: KeywordMetrics, raw: RawResult, now: datetime,
                    parser_version: str) -> None:
        self._db.execute(
            "INSERT INTO results (keyword_id, checked_at, has_data, search_volume, conversion_rate, "
            "competition_value, competition_kind, trend_json, related_json, raw_json, parser_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (keyword_id, _ts(now), int(metrics.has_data), metrics.search_volume, metrics.conversion_rate,
             metrics.competition_value, metrics.competition_kind, json.dumps(list(metrics.trend)),
             json.dumps(list(metrics.related), ensure_ascii=False),
             json.dumps(dataclasses.asdict(raw), ensure_ascii=False, default=str), parser_version))
        status = "done" if metrics.has_data else "no_data"
        self._db.execute("UPDATE keywords SET status = ?, last_checked_at = ?, fail_count = 0 WHERE id = ?",
                         (status, _ts(now), keyword_id))

    def _result_row(self, row: sqlite3.Row) -> ResultRow:
        metrics = KeywordMetrics(
            has_data=bool(row["has_data"]), search_volume=row["search_volume"],
            conversion_rate=row["conversion_rate"], competition_value=row["competition_value"],
            competition_kind=row["competition_kind"], trend=tuple(json.loads(row["trend_json"] or "[]")),
            related=tuple(json.loads(row["related_json"] or "[]")))
        return ResultRow(keyword_id=row["keyword_id"], keyword=row["keyword"], source=row["source"],
                         depth=row["depth"], parent_keyword=row["parent_keyword"], status=row["status"],
                         checked_at=_dt(row["checked_at"]), metrics=metrics)

    _RESULT_SELECT = """
        SELECT r.*, k.keyword, k.source, k.depth, k.status, p.keyword AS parent_keyword
        FROM results r JOIN keywords k ON r.keyword_id = k.id LEFT JOIN keywords p ON k.parent_id = p.id
    """

    def latest_results(self) -> list[ResultRow]:
        rows = self._db.execute(
            self._RESULT_SELECT + " WHERE r.id = (SELECT r2.id FROM results r2 WHERE r2.keyword_id = r.keyword_id "
            "ORDER BY r2.checked_at DESC, r2.id DESC LIMIT 1) ORDER BY k.keyword").fetchall()
        return [self._result_row(r) for r in rows]

    def all_results(self) -> list[ResultRow]:
        rows = self._db.execute(self._RESULT_SELECT + " ORDER BY r.checked_at DESC, r.id DESC").fetchall()
        return [self._result_row(r) for r in rows]

    # --- sesi --------------------------------------------------------------
    def start_session(self, now: datetime) -> int:
        return self._db.execute("INSERT INTO sessions (started_at) VALUES (?)", (_ts(now),)).lastrowid

    def increment_checked(self, session_id: int) -> None:
        self._db.execute("UPDATE sessions SET checked_count = checked_count + 1 WHERE id = ?", (session_id,))

    def end_session(self, session_id: int, now: datetime, stop_reason: str,
                    cooldown_until: datetime | None) -> None:
        self._db.execute(
            "UPDATE sessions SET ended_at = ?, stop_reason = ?, cooldown_until = ? WHERE id = ?",
            (_ts(now), stop_reason, _ts(cooldown_until) if cooldown_until else None, session_id))

    def checked_on(self, day: date, tz: tzinfo) -> int:
        rows = self._db.execute("SELECT started_at, checked_count FROM sessions").fetchall()
        return sum(count for started, count in rows if _dt(started).astimezone(tz).date() == day)

    def active_cooldown_until(self, now: datetime) -> datetime | None:
        rows = self._db.execute("SELECT cooldown_until FROM sessions WHERE cooldown_until IS NOT NULL").fetchall()
        active = [dt for (text,) in rows if (dt := _dt(text)) > now]
        return max(active) if active else None

    def last_session(self) -> dict | None:
        row = self._db.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return {"started_at": _dt(row["started_at"]), "ended_at": _dt(row["ended_at"]),
                "checked_count": row["checked_count"], "stop_reason": row["stop_reason"],
                "cooldown_until": _dt(row["cooldown_until"])}
