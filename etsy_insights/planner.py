"""Memilih keyword berikutnya yang dicari (spec §16.3)."""
from __future__ import annotations

from collections.abc import Collection
from datetime import datetime

from .config import Config
from .models import QueueItem, ResultRow
from .score import score_all
from .store import Store


def _ranked_harvested(store: Store, cfg: Config, candidates: list[ResultRow]) -> list[QueueItem]:
    """Kandidat panen yang layak, diurutkan menurut skor peluang atas seluruh data."""
    if not candidates:
        return []
    wanted = {row.keyword_id for row in candidates}
    ranked = [s.row for s in score_all(store.latest_results(), cfg) if s.eligible and s.row.keyword_id in wanted]
    items = [store.get(row.keyword) for row in ranked]
    return [item for item in items if item is not None]


def select_next(store: Store, cfg: Config, now: datetime,
                exclude_ids: Collection[int] = ()) -> QueueItem | None:
    user = store.next_user_pending(exclude_ids)
    if user is not None:
        return user
    ranked = _ranked_harvested(store, cfg, store.harvest_candidates(cfg.kedalaman_maks, exclude_ids))
    if ranked:
        return ranked[0]
    return store.next_recheck(now, cfg.cek_ulang_setelah_hari, exclude_ids)


def upcoming(store: Store, cfg: Config, limit: int = 50) -> list[QueueItem]:
    queue = store.pending_queue() + _ranked_harvested(store, cfg, store.harvest_candidates(cfg.kedalaman_maks))
    return queue[:limit]
