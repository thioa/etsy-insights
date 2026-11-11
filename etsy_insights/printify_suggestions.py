"""Usulan keyword awal dari Printify: tags produk pengguna dan kata produk (spec Tahap 4 §9)."""
from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from .printify_store import OwnProduct, ProductType
from .store import normalize_keyword


@dataclass(frozen=True)
class Suggestion:
    keyword: str
    origin: str  # "product word" | "tag on N products"


def suggest(types: Sequence[ProductType], products: Sequence[OwnProduct], existing: Collection[str],
            limit: int = 100) -> list[Suggestion]:
    seen = {normalize_keyword(k) for k in existing}
    tag_counts: Counter[str] = Counter()
    for product in products:
        tag_counts.update({normalize_keyword(tag) for tag in product.tags} - {""})
    result: list[Suggestion] = []
    for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0])):
        if tag not in seen:
            seen.add(tag)
            result.append(Suggestion(tag, f"tag on {count} product{'' if count == 1 else 's'}"))
    seeds = sorted({seed for t in types if t.available and t.words
                    for seed in (t.words[0], f"custom {t.words[0]}", f"personalized {t.words[0]}")})
    for seed in seeds:
        if seed not in seen:
            seen.add(seed)
            result.append(Suggestion(seed, "product word"))
    return result[:limit]
