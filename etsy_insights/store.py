"""Database SQLite lokal: antrean keyword, hasil, dan sesi."""
from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from collections.abc import Collection, Iterable, Sequence
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

from .models import CapturedResponse, KeywordMetrics, QueueItem, RawResult, RelatedKeyword, ResultRow
from .printify_store import PRINTIFY_SCHEMA, migrate_printify

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
    parser_version TEXT,
    kind TEXT NOT NULL DEFAULT 'search',
    conversion_level INTEGER,
    wow_pct REAL
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
# Status antrean saat sebuah keyword dikembalikan: keyword Anda menunggu, keyword panen kembali ke panen.
_QUEUE_STATUS = "CASE source WHEN 'user' THEN 'pending' ELSE 'harvested' END"
_REUSABLE_PANEN_STATUSES = ("pending", "harvested", "failed")
_MIGRATIONS = (("kind", "TEXT NOT NULL DEFAULT 'search'"), ("conversion_level", "INTEGER"), ("wow_pct", "REAL"))


def normalize_keyword(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _decode_text(data: bytes) -> str:
    """UTF-16 (dengan BOM), UTF-8, lalu Mac Roman sebagai cadangan (file dari Excel Mac)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("mac_roman")


def read_keywords_file(path: Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    seen: dict[str, None] = {}
    for line in _decode_text(path.read_bytes()).splitlines():
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
        self._path = str(Path(path).resolve()) if str(path) != ":memory:" else f":memory:{id(self)}"
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        if str(path) != ":memory:":
            # WAL: server web bisa membaca sementara proses sesi menulis.
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.executescript(PRINTIFY_SCHEMA)
        migrate_printify(self._db)
        self._migrate()

    def _migrate(self) -> None:
        """Tambahkan kolom baru ke database lama (dibuat oleh versi sebelumnya)."""
        existing = {row[1] for row in self._db.execute("PRAGMA table_info(results)")}
        for name, ddl in _MIGRATIONS:
            if name not in existing:
                self._db.execute(f"ALTER TABLE results ADD COLUMN {name} {ddl}")
        # Tanpa indeks ini, "hasil terbaru per keyword" memindai seluruh tabel untuk setiap baris.
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_results_keyword ON results(keyword_id, checked_at, id)")

    def close(self) -> None:
        self._db.close()

    @property
    def path(self) -> str:
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        return self._db

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
                status = "pending" if existing.status == "harvested" else existing.status
                self._db.execute(
                    "UPDATE keywords SET source = 'user', parent_id = NULL, depth = 0, status = ? WHERE id = ?",
                    (status, existing.id))
                changed += 1
        return changed

    def pending_queue(self) -> list[QueueItem]:
        rows = self._db.execute(
            f"SELECT {_KEYWORD_COLUMNS} FROM keywords k LEFT JOIN keywords p ON k.parent_id = p.id "
            f"WHERE k.status = 'pending' ORDER BY {_QUEUE_ORDER}").fetchall()
        return [self._queue_item(r) for r in rows]

    def mark_in_progress(self, keyword_id: int) -> None:
        self._db.execute("UPDATE keywords SET status = 'in_progress' WHERE id = ?", (keyword_id,))

    def return_to_queue(self, keyword_id: int) -> None:
        self._db.execute(f"UPDATE keywords SET status = {_QUEUE_STATUS} WHERE id = ?", (keyword_id,))

    def recover_in_progress(self) -> int:
        return self._db.execute(
            f"UPDATE keywords SET status = {_QUEUE_STATUS} WHERE status = 'in_progress'").rowcount

    def record_failure(self, keyword_id: int) -> str:
        self._db.execute("UPDATE keywords SET fail_count = fail_count + 1 WHERE id = ?", (keyword_id,))
        fails, source = self._db.execute(
            "SELECT fail_count, source FROM keywords WHERE id = ?", (keyword_id,)).fetchone()
        if fails >= MAX_FAILURES:
            status = "failed"
        else:
            status = "pending" if source == "user" else "harvested"
        self._db.execute("UPDATE keywords SET status = ? WHERE id = ?", (status, keyword_id))
        return status

    def next_user_pending(self, exclude_ids: Collection[int] = ()) -> QueueItem | None:
        exclude = list(exclude_ids)
        not_in = f"AND k.id NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        row = self._db.execute(
            f"SELECT {_KEYWORD_COLUMNS} FROM keywords k LEFT JOIN keywords p ON k.parent_id = p.id "
            f"WHERE k.status = 'pending' {not_in} ORDER BY {_QUEUE_ORDER} LIMIT 1", exclude).fetchone()
        return self._queue_item(row) if row else None

    def next_recheck(self, now: datetime, recheck_days: int,
                     exclude_ids: Collection[int] = ()) -> QueueItem | None:
        exclude = list(exclude_ids)
        not_in = f"AND k.id NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        row = self._db.execute(
            f"SELECT {_KEYWORD_COLUMNS} FROM keywords k LEFT JOIN keywords p ON k.parent_id = p.id "
            f"WHERE k.status IN ('done', 'no_data') AND k.last_checked_at < ? {not_in} "
            "ORDER BY k.last_checked_at, k.id LIMIT 1",
            [_ts(now - timedelta(days=recheck_days)), *exclude]).fetchone()
        return self._queue_item(row) if row else None

    def harvest_candidates(self, max_depth: int, exclude_ids: Collection[int] = ()) -> list[ResultRow]:
        """Hasil terbaru keyword panen yang boleh dicari (kedalaman < max_depth)."""
        exclude = list(exclude_ids)
        not_in = f"AND k.id NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        rows = self._db.execute(
            self._RESULT_SELECT + f" WHERE k.status = 'harvested' AND k.depth < ? {not_in} AND r.id = "
            "(SELECT r2.id FROM results r2 WHERE r2.keyword_id = r.keyword_id "
            "ORDER BY r2.checked_at DESC, r2.id DESC LIMIT 1) ORDER BY k.keyword", [max_depth, *exclude]).fetchall()
        return [self._result_row(r) for r in rows]

    def remove_user_keyword(self, keyword_id: int) -> None:
        """Kembalikan keyword ke hasil panen (kalau punya data panen); kalau tidak punya hasil, hapus."""
        has_panen = self._db.execute(
            "SELECT 1 FROM results WHERE keyword_id = ? AND kind = 'panen' LIMIT 1", (keyword_id,)).fetchone()
        if has_panen:
            self._db.execute(
                "UPDATE keywords SET source = 'related', depth = 1, status = 'harvested' WHERE id = ?", (keyword_id,))
            return
        has_results = self._db.execute("SELECT 1 FROM results WHERE keyword_id = ? LIMIT 1", (keyword_id,)).fetchone()
        if not has_results:
            self._db.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))

    def change_stamp(self) -> tuple:
        """Cheap fingerprint that changes whenever keywords or results change (used to cache queue ranking)."""
        results = tuple(self._db.execute("SELECT COUNT(*), MAX(id), MAX(checked_at) FROM results").fetchone())
        keywords = tuple(self._db.execute(
            "SELECT COUNT(*), TOTAL(id * instr('pending|in_progress|done|no_data|harvested|failed|', status || '|')), "
            "TOTAL(id * depth), TOTAL(id * (source = 'user')), TOTAL(id * (parent_id IS NULL)) FROM keywords"
        ).fetchone())
        return results + keywords

    def keyword_statuses(self) -> dict[str, str]:
        """keyword -> status (pending, in_progress, done, no_data, harvested, …)."""
        return {row[0]: row[1] for row in self._db.execute("SELECT keyword, status FROM keywords")}

    def keyword_texts(self) -> set[str]:
        """Semua keyword di database (status apa pun)."""
        return {row[0] for row in self._db.execute("SELECT keyword FROM keywords")}

    def status_counts(self) -> dict[str, int]:
        rows = self._db.execute("SELECT status, COUNT(*) FROM keywords GROUP BY status").fetchall()
        return {status: count for status, count in rows if count > 0}

    # --- hasil -------------------------------------------------------------
    def save_result(self, keyword_id: int, metrics: KeywordMetrics, raw: RawResult, now: datetime,
                    parser_version: str) -> None:
        self._db.execute(
            "INSERT INTO results (keyword_id, checked_at, has_data, search_volume, conversion_rate, "
            "competition_value, competition_kind, trend_json, related_json, raw_json, parser_version, "
            "kind, conversion_level, wow_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'search', ?, ?)",
            (keyword_id, _ts(now), int(metrics.has_data), metrics.search_volume, metrics.conversion_rate,
             metrics.competition_value, metrics.competition_kind, json.dumps(list(metrics.trend)),
             json.dumps(list(metrics.related), ensure_ascii=False),
             json.dumps(dataclasses.asdict(raw), ensure_ascii=False, default=str), parser_version,
             metrics.conversion_level, metrics.wow_pct))
        status = "done" if metrics.has_data else "no_data"
        self._db.execute("UPDATE keywords SET status = ?, last_checked_at = ?, fail_count = 0 WHERE id = ?",
                         (status, _ts(now), keyword_id))

    def save_harvest(self, parent_id: int, related: Sequence[RelatedKeyword], max_count: int, max_depth: int,
                     now: datetime) -> int:
        """Simpan keyword terkait beserta datanya. Mengembalikan jumlah keyword baru."""
        parent = self._db.execute("SELECT depth FROM keywords WHERE id = ?", (parent_id,)).fetchone()
        if parent is None or parent["depth"] + 1 > max_depth:
            return 0
        unique: dict[str, RelatedKeyword] = {}
        for item in related:
            keyword = normalize_keyword(item.keyword)
            if keyword:
                unique.setdefault(keyword, item)
        added = 0
        for keyword, item in list(unique.items())[:max_count]:
            existing = self._db.execute("SELECT id, status FROM keywords WHERE keyword = ?", (keyword,)).fetchone()
            if existing is None:
                keyword_id = self._db.execute(
                    "INSERT INTO keywords (keyword, source, parent_id, depth, status, added_at) "
                    "VALUES (?, 'related', ?, ?, 'harvested', ?)",
                    (keyword, parent_id, parent["depth"] + 1, _ts(now))).lastrowid
                added += 1
            elif existing["status"] in _REUSABLE_PANEN_STATUSES:
                keyword_id = existing["id"]
                self._db.execute("DELETE FROM results WHERE keyword_id = ? AND kind = 'panen'", (keyword_id,))
            else:
                continue
            self._db.execute(
                "INSERT INTO results (keyword_id, checked_at, has_data, search_volume, competition_value, "
                "competition_kind, trend_json, related_json, kind, conversion_level) "
                "VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', 'panen', ?)",
                (keyword_id, _ts(now), int(bool(item.search_volume)), item.search_volume, item.competition_value,
                 "count" if item.competition_value is not None else None, item.conversion_level))
        return added

    def _result_row(self, row: sqlite3.Row) -> ResultRow:
        metrics = KeywordMetrics(
            has_data=bool(row["has_data"]), search_volume=row["search_volume"],
            conversion_rate=row["conversion_rate"], competition_value=row["competition_value"],
            competition_kind=row["competition_kind"], trend=tuple(json.loads(row["trend_json"] or "[]")),
            related=tuple(json.loads(row["related_json"] or "[]")),
            conversion_level=row["conversion_level"], wow_pct=row["wow_pct"])
        return ResultRow(keyword_id=row["keyword_id"], keyword=row["keyword"], source=row["source"],
                         depth=row["depth"], parent_keyword=row["parent_keyword"], status=row["status"],
                         checked_at=_dt(row["checked_at"]), metrics=metrics, kind=row["kind"])

    _RESULT_SELECT = """
        SELECT r.id, r.keyword_id, r.checked_at, r.has_data, r.search_volume, r.conversion_rate,
               r.competition_value, r.competition_kind, r.trend_json, r.related_json, r.kind,
               r.conversion_level, r.wow_pct, k.keyword, k.source, k.depth, k.status, p.keyword AS parent_keyword
        FROM results r JOIN keywords k ON r.keyword_id = k.id LEFT JOIN keywords p ON k.parent_id = p.id
    """

    def latest_results(self) -> list[ResultRow]:
        rows = self._db.execute(
            self._RESULT_SELECT + " WHERE r.id = (SELECT r2.id FROM results r2 WHERE r2.keyword_id = r.keyword_id "
            "ORDER BY r2.checked_at DESC, r2.id DESC LIMIT 1) ORDER BY k.keyword").fetchall()
        return [self._result_row(r) for r in rows]

    def harvested_from(self, parent_id: int, limit: int = 50) -> list[ResultRow]:
        """Hasil terbaru keyword yang dipanen dari induk ini, volume terbesar dulu."""
        rows = self._db.execute(
            self._RESULT_SELECT + " WHERE k.parent_id = ? AND r.id = (SELECT r2.id FROM results r2 "
            "WHERE r2.keyword_id = r.keyword_id ORDER BY r2.checked_at DESC, r2.id DESC LIMIT 1) "
            "ORDER BY r.search_volume DESC, k.keyword LIMIT ?", (parent_id, limit)).fetchall()
        return [self._result_row(r) for r in rows]

    def latest_search_raw(self, keyword_id: int) -> RawResult | None:
        """Data mentah pencarian terbaru untuk satu keyword (untuk halaman detail)."""
        row = self._db.execute(
            "SELECT raw_json FROM results WHERE keyword_id = ? AND kind = 'search' AND raw_json IS NOT NULL "
            "ORDER BY checked_at DESC, id DESC LIMIT 1", (keyword_id,)).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return RawResult(data["keyword"], data["page_url"],
                         tuple(CapturedResponse(r["url"], r["status"], r["body"]) for r in data["responses"]),
                         data.get("html", ""))

    def latest_search_raws(self) -> dict[int, RawResult]:
        """keyword_id -> data mentah dari pencarian terbaru (dipakai untuk profil selera)."""
        rows = self._db.execute(
            "SELECT r.keyword_id, r.raw_json FROM results r WHERE r.kind = 'search' AND r.raw_json IS NOT NULL "
            "AND r.id = (SELECT r2.id FROM results r2 WHERE r2.keyword_id = r.keyword_id AND r2.kind = 'search' "
            "AND r2.raw_json IS NOT NULL ORDER BY r2.checked_at DESC, r2.id DESC LIMIT 1)").fetchall()
        raws = {}
        for keyword_id, text in rows:
            data = json.loads(text)
            raws[keyword_id] = RawResult(
                data["keyword"], data["page_url"],
                tuple(CapturedResponse(r["url"], r["status"], r["body"]) for r in data["responses"]),
                data.get("html", ""))
        return raws

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

    def stop_reasons_on(self, day: date, tz: tzinfo) -> list[str]:
        rows = self._db.execute(
            "SELECT started_at, stop_reason FROM sessions WHERE stop_reason IS NOT NULL ORDER BY id").fetchall()
        return [reason for started, reason in rows if _dt(started).astimezone(tz).date() == day]

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
