"""Memilih keyword berikutnya yang dicari (spec §16.3)."""
from __future__ import annotations

from collections.abc import Collection
from datetime import datetime

from .config import Config
from .models import QueueItem, ResultRow
from .score import score_all
from .store import Store


def _ranked_harvested(store: Store, cfg: Config, candidates: list[ResultRow], limit: int) -> list[QueueItem]:
    """Kandidat panen yang layak, diurutkan menurut skor peluang atas seluruh data (maks `limit`)."""
    if not candidates or limit <= 0:
        return []
    wanted = {row.keyword_id for row in candidates}
    ranked = [s.row for s in score_all(store.latest_results(), cfg) if s.eligible and s.row.keyword_id in wanted]
    items = []
    for row in ranked:
        item = store.get(row.keyword)
        if item is not None:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def select_next(store: Store, cfg: Config, now: datetime,
                exclude_ids: Collection[int] = ()) -> QueueItem | None:
    user = store.next_user_pending(exclude_ids)
    if user is not None:
        return user
    ranked = _ranked_harvested(store, cfg, store.harvest_candidates(cfg.kedalaman_maks, exclude_ids), limit=1)
    if ranked:
        return ranked[0]
    return store.next_recheck(now, cfg.cek_ulang_setelah_hari, exclude_ids)


def upcoming(store: Store, cfg: Config, limit: int = 50) -> list[QueueItem]:
    pending = store.pending_queue()[:limit]
    return pending + _ranked_harvested(store, cfg, store.harvest_candidates(cfg.kedalaman_maks), limit - len(pending))
