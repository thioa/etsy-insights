"""Kecocokan keyword ↔ jenis produk Printify beserta margin dan label Ready to sell (spec Tahap 4 §7–§8)."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .config import Config
from .margin import NO_MATCH, Fees, Margin, compute, is_ready, paid_price_cents
from .printify_store import ProductType
from .product_words import normalize_words


@dataclass(frozen=True)
class Candidate:
    type: ProductType
    margin: Margin


@dataclass(frozen=True)
class ProductFit:
    primary: ProductType | None
    margin: Margin
    candidates: tuple[Candidate, ...]
    ready: bool
    linked: bool


def _cents(usd: float) -> int:
    return int(Decimal(str(usd)).scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def fees_from_config(cfg: Config) -> Fees:
    return Fees(cfg.fee_etsy_persen, _cents(cfg.fee_etsy_tetap_usd))


def minimum_cents(cfg: Config) -> int:
    return _cents(cfg.margin_minimum_usd)


def _order(candidate: Candidate) -> tuple:
    margin, kind = candidate.margin, candidate.type
    ok = margin.status == "ok"
    return (not ok, -(margin.margin_cents or 0) if ok else 0, kind.source != "own",
            kind.cost_min_cents is None, kind.cost_min_cents or 0, kind.id)


class _Matcher:
    """Mencocokkan banyak keyword sekaligus: frasa tiap jenis produk dinormalkan sekali, keyword dipecah n-gram."""

    def __init__(self, types: Sequence[ProductType]) -> None:
        self.types = list(types)
        self.index: dict[tuple[str, ...], set[int]] = {}
        for t in self.types:
            if t.available:
                for word in t.words:
                    phrase = normalize_words(word)
                    if phrase:
                        self.index.setdefault(phrase, set()).add(t.id)
        self.max_len = max((len(p) for p in self.index), default=0)

    def matching(self, tokens: Sequence[str]) -> list[ProductType]:
        found: set[int] = set()
        for n in range(1, self.max_len + 1):
            for i in range(len(tokens) - n + 1):
                found.update(self.index.get(tuple(tokens[i:i + n]), ()))
        return [t for t in self.types if t.id in found] if found else []


def _fit(tokens: Sequence[str], label: str, price_cents: int | None, matcher: _Matcher,
         linked_type_id: int | None, fees: Fees, minimum: int) -> ProductFit:
    if linked_type_id is not None:
        chosen = [t for t in matcher.types if t.id == linked_type_id and t.available]
    else:
        chosen = matcher.matching(tokens)
    linked = linked_type_id is not None
    if not chosen:
        return ProductFit(None, NO_MATCH, (), False, linked)
    candidates = sorted((Candidate(t, compute(price_cents, t.cost_min_cents, t.shipping_us_cents, fees, minimum))
                         for t in chosen), key=_order)
    best = candidates[0]
    return ProductFit(best.type, best.margin, tuple(candidates), is_ready(label, best.margin, minimum), linked)


def fit_keyword(keyword: str, label: str, price_cents: int | None, types: Sequence[ProductType],
                linked_type_id: int | None, fees: Fees, minimum: int) -> ProductFit:
    return _fit(normalize_words(keyword), label, price_cents, _Matcher(types), linked_type_id, fees, minimum)


def fit_all(scored: Sequence, profiles: Mapping, types: Sequence[ProductType], links: Mapping[str, int],
            cfg: Config) -> dict[str, ProductFit]:
    """ProductFit per keyword (kunci: teks keyword). `scored` berisi ScoredKeyword, `profiles` TasteProfile."""
    fees, minimum = fees_from_config(cfg), minimum_cents(cfg)
    matcher = _Matcher(types)
    fits: dict[str, ProductFit] = {}
    for item in scored:
        keyword = item.row.keyword
        profile = profiles.get(keyword)
        price = paid_price_cents(profile.paid_price_low, profile.paid_price_high) if profile else None
        fits[keyword] = _fit(normalize_words(keyword), item.label, price, matcher, links.get(keyword), fees, minimum)
    return fits


def match_counts(keywords: Iterable[str], types: Sequence[ProductType], links: Mapping[str, int]) -> dict[int, int]:
    counts = {t.id: 0 for t in types}
    matcher = _Matcher(types)
    for keyword in keywords:
        linked = links.get(keyword)
        if linked is not None:
            if linked in counts:
                counts[linked] += 1
            continue
        for kind in matcher.matching(normalize_words(keyword)):
            counts[kind.id] += 1
    return counts
