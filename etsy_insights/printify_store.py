"""Data Printify di etsy.db: jenis produk, produk pengguna, katalog, tautan manual (spec Tahap 4 §6)."""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .product_words import words_for_title

if TYPE_CHECKING:
    from .store import Store

PRINTIFY_SCHEMA = """
CREATE TABLE IF NOT EXISTS printify_meta (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS printify_blueprints (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, brand TEXT, model TEXT
);
CREATE TABLE IF NOT EXISTS printify_types (
    id INTEGER PRIMARY KEY,
    blueprint_id INTEGER NOT NULL,
    print_provider_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    provider_title TEXT,
    source TEXT NOT NULL,
    cost_min_cents INTEGER,
    cost_max_cents INTEGER,
    shipping_us_cents INTEGER,
    handling_days INTEGER,
    words_json TEXT NOT NULL,
    words_edited INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 1,
    synced_at TEXT,
    UNIQUE (blueprint_id, print_provider_id)
);
CREATE TABLE IF NOT EXISTS printify_products (
    id TEXT PRIMARY KEY,
    type_id INTEGER NOT NULL REFERENCES printify_types(id),
    title TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    cost_min_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS keyword_product_links (
    keyword_id INTEGER PRIMARY KEY REFERENCES keywords(id),
    type_id INTEGER NOT NULL REFERENCES printify_types(id)
);
"""


@dataclass(frozen=True)
class Blueprint:
    id: int
    title: str
    brand: str
    model: str


@dataclass(frozen=True)
class SyncedProduct:
    id: str
    blueprint_id: int
    print_provider_id: int
    title: str
    tags: tuple[str, ...]
    cost_min_cents: int
    cost_max_cents: int


@dataclass(frozen=True)
class SyncedType:
    blueprint_id: int
    print_provider_id: int
    title: str
    provider_title: str | None
    source: str  # "own" | "picked"
    cost_min_cents: int | None
    cost_max_cents: int | None
    shipping_us_cents: int | None
    handling_days: int | None
    available: bool


@dataclass(frozen=True)
class SyncResult:
    shop_id: int
    shop_title: str
    blueprints: tuple[Blueprint, ...]
    products: tuple[SyncedProduct, ...]
    types: tuple[SyncedType, ...]


@dataclass(frozen=True)
class ProductType:
    id: int
    blueprint_id: int
    print_provider_id: int
    title: str
    provider_title: str | None
    source: str
    cost_min_cents: int | None
    cost_max_cents: int | None
    shipping_us_cents: int | None
    handling_days: int | None
    words: tuple[str, ...]
    words_edited: bool
    available: bool
    synced_at: datetime | None


@dataclass(frozen=True)
class OwnProduct:
    id: str
    type_id: int
    title: str
    tags: tuple[str, ...]
    cost_min_cents: int


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _dt(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _clean_words(words: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    for word in words:
        word = " ".join(str(word).split()).lower()
        if word and word not in cleaned:
            cleaned.append(word)
    return cleaned


_TYPE_COLUMNS = ("id, blueprint_id, print_provider_id, title, provider_title, source, cost_min_cents, "
                 "cost_max_cents, shipping_us_cents, handling_days, words_json, words_edited, available, synced_at")


class PrintifyStore:
    def __init__(self, store: Store) -> None:
        self._db = store.connection

    # --- meta ---------------------------------------------------------------
    def meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM printify_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str | None) -> None:
        if value is None:
            self._db.execute("DELETE FROM printify_meta WHERE key = ?", (key,))
        else:
            self._db.execute("INSERT OR REPLACE INTO printify_meta (key, value) VALUES (?, ?)", (key, value))

    # --- jenis produk -------------------------------------------------------
    @staticmethod
    def _type(row) -> ProductType:
        return ProductType(
            id=row[0], blueprint_id=row[1], print_provider_id=row[2], title=row[3], provider_title=row[4],
            source=row[5], cost_min_cents=row[6], cost_max_cents=row[7], shipping_us_cents=row[8],
            handling_days=row[9], words=tuple(json.loads(row[10])), words_edited=bool(row[11]),
            available=bool(row[12]), synced_at=_dt(row[13]))

    def types(self, include_unavailable: bool = True) -> list[ProductType]:
        where = "" if include_unavailable else "WHERE available = 1"
        rows = self._db.execute(
            f"SELECT {_TYPE_COLUMNS} FROM printify_types {where} "
            "ORDER BY source = 'picked', lower(title), id").fetchall()
        return [self._type(r) for r in rows]

    def type(self, type_id: int) -> ProductType | None:
        row = self._db.execute(f"SELECT {_TYPE_COLUMNS} FROM printify_types WHERE id = ?", (type_id,)).fetchone()
        return self._type(row) if row else None

    def _type_by_key(self, blueprint_id: int, provider_id: int) -> ProductType | None:
        row = self._db.execute(
            f"SELECT {_TYPE_COLUMNS} FROM printify_types WHERE blueprint_id = ? AND print_provider_id = ?",
            (blueprint_id, provider_id)).fetchone()
        return self._type(row) if row else None

    def picked_keys(self) -> list[tuple[int, int]]:
        rows = self._db.execute("SELECT blueprint_id, print_provider_id FROM printify_types "
                                "WHERE source = 'picked' ORDER BY id").fetchall()
        return [(r[0], r[1]) for r in rows]

    def add_picked(self, blueprint_id: int, print_provider_id: int, title: str, provider_title: str | None,
                   cost_cents: int | None, shipping_us_cents: int | None, handling_days: int | None,
                   now: datetime) -> ProductType:
        existing = self._type_by_key(blueprint_id, print_provider_id)
        if existing is not None:
            return existing
        cursor = self._db.execute(
            "INSERT INTO printify_types (blueprint_id, print_provider_id, title, provider_title, source, "
            "cost_min_cents, cost_max_cents, shipping_us_cents, handling_days, words_json, synced_at) "
            "VALUES (?, ?, ?, ?, 'picked', ?, ?, ?, ?, ?, ?)",
            (blueprint_id, print_provider_id, title, provider_title, cost_cents, cost_cents, shipping_us_cents,
             handling_days, json.dumps(words_for_title(title)), _ts(now)))
        return self.type(cursor.lastrowid)

    def update_type(self, type_id: int, *, words: Sequence[str] | None = None,
                    cost_cents: int | None = None) -> ProductType:
        current = self.type(type_id)
        if current is None:
            raise KeyError(type_id)
        if cost_cents is not None and current.source != "picked":
            raise ValueError("Cost can only be set for picked product types.")
        if words is not None:
            self._db.execute("UPDATE printify_types SET words_json = ?, words_edited = 1 WHERE id = ?",
                             (json.dumps(_clean_words(words)), type_id))
        if cost_cents is not None:
            self._db.execute("UPDATE printify_types SET cost_min_cents = ?, cost_max_cents = ? WHERE id = ?",
                             (cost_cents, cost_cents, type_id))
        return self.type(type_id)

    def remove_picked(self, type_id: int) -> bool:
        current = self.type(type_id)
        if current is None or current.source != "picked":
            return False
        self._db.execute("DELETE FROM keyword_product_links WHERE type_id = ?", (type_id,))
        self._db.execute("DELETE FROM printify_types WHERE id = ?", (type_id,))
        return True

    # --- sync ---------------------------------------------------------------
    def apply_sync(self, result: SyncResult, now: datetime) -> None:
        """Simpan hasil sync dalam satu transaksi (aturan spec §6). Editan pengguna dibaca di dalam transaksi."""
        db = self._db
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = {(t.blueprint_id, t.print_provider_id): t for t in self.types()}
            linked = {r[0] for r in db.execute("SELECT DISTINCT type_id FROM keyword_product_links")}
            synced_keys = set()
            for t in result.types:
                key = (t.blueprint_id, t.print_provider_id)
                synced_keys.add(key)
                current = existing.get(key)
                if current is None:
                    db.execute(
                        "INSERT INTO printify_types (blueprint_id, print_provider_id, title, provider_title, "
                        "source, cost_min_cents, cost_max_cents, shipping_us_cents, handling_days, words_json, "
                        "available, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (*key, t.title, t.provider_title, t.source, t.cost_min_cents, t.cost_max_cents,
                         t.shipping_us_cents, t.handling_days, json.dumps(words_for_title(t.title)),
                         int(t.available), _ts(now)))
                    continue
                title = t.title or current.title
                words = list(current.words) if current.words_edited else words_for_title(title)
                if t.source == "own":
                    source, low, high = "own", t.cost_min_cents, t.cost_max_cents
                else:
                    source, low, high = current.source, current.cost_min_cents, current.cost_max_cents
                db.execute(
                    "UPDATE printify_types SET title = ?, provider_title = ?, source = ?, cost_min_cents = ?, "
                    "cost_max_cents = ?, shipping_us_cents = ?, handling_days = ?, words_json = ?, "
                    "available = ?, synced_at = ? WHERE id = ?",
                    (title, t.provider_title or current.provider_title, source, low, high, t.shipping_us_cents,
                     t.handling_days, json.dumps(words), int(t.available), _ts(now), current.id))
            db.execute("DELETE FROM printify_products")
            for key, current in existing.items():
                if key in synced_keys or current.source != "own":
                    continue
                if current.id in linked:
                    db.execute("UPDATE printify_types SET source = 'picked' WHERE id = ?", (current.id,))
                else:
                    db.execute("DELETE FROM printify_types WHERE id = ?", (current.id,))
            for p in result.products:
                type_id = db.execute("SELECT id FROM printify_types WHERE blueprint_id = ? AND "
                                     "print_provider_id = ?", (p.blueprint_id, p.print_provider_id)).fetchone()[0]
                db.execute("INSERT OR REPLACE INTO printify_products (id, type_id, title, tags_json, cost_min_cents) "
                           "VALUES (?, ?, ?, ?, ?)", (p.id, type_id, p.title, json.dumps(list(p.tags)), p.cost_min_cents))
            db.execute("DELETE FROM printify_blueprints")
            db.executemany("INSERT OR REPLACE INTO printify_blueprints (id, title, brand, model) VALUES (?, ?, ?, ?)",
                           [(b.id, b.title, b.brand, b.model) for b in result.blueprints])
            self.set_meta("shop_id", str(result.shop_id))
            self.set_meta("shop_title", result.shop_title)
            self.set_meta("last_sync_at", _ts(now))
            self.set_meta("last_sync_error", None)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    def record_sync_error(self, message: str) -> None:
        self.set_meta("last_sync_error", message)

    # --- produk, katalog, tautan --------------------------------------------
    def products(self) -> list[OwnProduct]:
        rows = self._db.execute("SELECT id, type_id, title, tags_json, cost_min_cents FROM printify_products "
                                "ORDER BY id").fetchall()
        return [OwnProduct(r[0], r[1], r[2], tuple(json.loads(r[3])), r[4]) for r in rows]

    def has_blueprints(self) -> bool:
        return self._db.execute("SELECT 1 FROM printify_blueprints LIMIT 1").fetchone() is not None

    def search_blueprints(self, query: str, limit: int = 30) -> list[Blueprint]:
        pattern = f"%{' '.join(query.split())}%"
        rows = self._db.execute(
            "SELECT id, title, brand, model FROM printify_blueprints "
            "WHERE title || ' ' || coalesce(brand, '') || ' ' || coalesce(model, '') LIKE ? "
            "ORDER BY lower(title), id LIMIT ?", (pattern, limit)).fetchall()
        return [Blueprint(r[0], r[1], r[2] or "", r[3] or "") for r in rows]

    def link(self, keyword_id: int, type_id: int | None) -> None:
        if type_id is None:
            self._db.execute("DELETE FROM keyword_product_links WHERE keyword_id = ?", (keyword_id,))
        else:
            self._db.execute("INSERT OR REPLACE INTO keyword_product_links (keyword_id, type_id) VALUES (?, ?)",
                             (keyword_id, type_id))

    def links(self) -> dict[str, int]:
        rows = self._db.execute("SELECT k.keyword, l.type_id FROM keyword_product_links l "
                                "JOIN keywords k ON k.id = l.keyword_id").fetchall()
        return {r[0]: r[1] for r in rows}
