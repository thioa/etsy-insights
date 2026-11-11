"""Ritme seperti manusia, kuota harian, dan masa pendinginan."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .config import Config

HESITATION_CHANCE = 0.10
HESITATION_MS = (300, 900)
SCROLL_CHANCE = 0.5


class Pacer:
    def __init__(self, cfg: Config, rng: random.Random) -> None:
        self._cfg = cfg
        self._rng = rng

    def _uniform(self, bounds: tuple[float, float]) -> float:
        return self._rng.uniform(*bounds)

    def typing_delay_ms(self) -> float:
        delay = self._uniform(self._cfg.kecepatan_ketik_ms)
        if self._rng.random() < HESITATION_CHANCE:
            delay += self._uniform(HESITATION_MS)
        return delay

    def dwell_seconds(self) -> float:
        return self._uniform(self._cfg.waktu_baca_detik)

    def should_scroll(self) -> bool:
        return self._rng.random() < SCROLL_CHANCE

    def gap_seconds(self) -> float:
        return self._uniform(self._cfg.jeda_antar_keyword_detik)

    def break_every(self) -> int:
        lo, hi = self._cfg.istirahat_setiap
        return self._rng.randint(int(lo), int(hi))

    def break_seconds(self) -> float:
        return self._uniform(self._cfg.istirahat_detik)


def remaining_quota(cfg: Config, checked_today: int, max_keywords: int | None = None) -> int:
    left = max(0, cfg.kuota_harian - checked_today)
    return min(left, max_keywords) if max_keywords is not None else left


def cooldown_end(now: datetime, cfg: Config) -> datetime:
    return now + timedelta(hours=cfg.pendinginan_jam)
