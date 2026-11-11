"""Katalog Printify per kategori: ringkasan peluang Etsy dan Research (spec Tahap 5 §5–§7)."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Config
from .keywords import add_keywords
from .printify_api import PrintifyClient
from .printify_store import Blueprint, PrintifyStore, ShippingInfo
from .printify_sync import check_shipping, handling_days, us_shipping_cents
from .product_fit import fits_for_store
from .product_words import CATEGORY_NAMES, ENTRIES, category_for, category_slug, normalize_words
from .score import ScoredKeyword, score_all
from .store import Store
from .taste import build_profiles

OTHER = "other"
SEARCHED = ("done", "no_data")
WAITING = ("pending", "in_progress")
TOP_KEYWORDS = 10


@dataclass(frozen=True)
class CategoryInfo:
    main: str
    slug: str
    name: str
    blueprints: tuple[Blueprint, ...]
    photo: str


@dataclass(frozen=True)
class ResearchState:
    status: str  # available | in_queue | researched | none
    pending: int


@dataclass(frozen=True)
class CategorySummary:
    info: CategoryInfo
    keywords: int
    searched: int
    status: str  # not_researched | harvested_only | researched
    most_searched: tuple[str, int] | None
    gold: int
    potential: int
    best: tuple[str, float, str] | None
    ready: int | None
    models: int
    in_my_products: bool
    research: ResearchState
    top: tuple[ScoredKeyword, ...] = ()  # 10 keyword terbaik (untuk halaman kategori)


def categories_from(blueprints: Sequence[Blueprint]) -> dict[str, CategoryInfo]:
    groups: dict[str, list[Blueprint]] = {}
    for blueprint in sorted(blueprints, key=lambda b: (b.title.lower(), b.id)):
        groups.setdefault(category_for(blueprint.title), []).append(blueprint)
    return {main: CategoryInfo(main, category_slug(main), CATEGORY_NAMES.get(main, main.title()), tuple(items),
                               next((b.image_url for b in items if b.image_url), ""))
            for main, items in groups.items()}


def research_seeds(main: str) -> list[str]:
    return [main, f"custom {main}", f"personalized {main}"]


def _needs_research(status: str | None) -> bool:
    return status is None or status == "harvested"


def research_state(statuses: Mapping[str, str], main: str) -> ResearchState:
    if main == OTHER or main not in ENTRIES:
        return ResearchState("none", 0)
    seeds = research_seeds(main)
    if any(_needs_research(statuses.get(seed)) for seed in seeds):
        return ResearchState("available", 0)
    pending = sum(statuses.get(seed) in WAITING for seed in seeds)
    return ResearchState("in_queue", pending) if pending else ResearchState("researched", 0)


def research(home: Path, store: Store, main: str, now: datetime) -> list[str]:
    """Kirim keyword awal yang perlu diriset ke antrean (sebagai keyword pengguna). Kembalikan yang dikirim."""
    statuses = store.keyword_statuses()
    needed = [seed for seed in research_seeds(main) if _needs_research(statuses.get(seed))]
    if needed:
        add_keywords(home, store, "\n".join(needed), now)
    return needed


class _CategoryIndex:
    """Satu indeks frasa untuk semua kategori: keyword → kategori yang kata-katanya ada di keyword itu."""

    def __init__(self, mains: Iterable[str]) -> None:
        self.index: dict[tuple[str, ...], set[str]] = {}
        for main in mains:
            for word in ENTRIES.get(main, ()):
                phrase = normalize_words(word)
                if phrase:
                    self.index.setdefault(phrase, set()).add(main)
        self.max_len = max((len(p) for p in self.index), default=0)

    def categories(self, keyword: str) -> set[str]:
        tokens = normalize_words(keyword)
        found: set[str] = set()
        for n in range(1, self.max_len + 1):
            for i in range(len(tokens) - n + 1):
                found.update(self.index.get(tuple(tokens[i:i + n]), ()))
        return found


_CACHE: dict[str, tuple[tuple, dict[str, CategorySummary]]] = {}


def summarize(store: Store, cfg: Config, categories: Mapping[str, CategoryInfo]) -> dict[str, CategorySummary]:
    """Ringkasan per kategori. Disimpan sampai keyword, hasil, data Printify, atau pengaturan berubah."""
    printify = PrintifyStore(store)
    key = (store.change_stamp(), tuple(printify.types()), tuple(sorted(printify.links().items())), cfg,
           tuple(sorted(categories.items())))
    cached = _CACHE.get(store.path)
    if cached is not None and cached[0] == key:
        return cached[1]
    summaries = _summarize(store, cfg, categories, printify)
    _CACHE[store.path] = (key, summaries)
    return summaries


def _summarize(store: Store, cfg: Config, categories: Mapping[str, CategoryInfo],
               printify: PrintifyStore) -> dict[str, CategorySummary]:
    statuses = store.keyword_statuses()
    scored = score_all(store.latest_results(), cfg)
    types = [t for t in printify.types() if t.available]
    mine = {category_for(t.title) for t in types}
    costed = {category_for(t.title) for t in types if t.cost_min_cents is not None}
    index = _CategoryIndex(m for m in categories if m != OTHER)
    members: dict[str, list[ScoredKeyword]] = {main: [] for main in categories}
    for item in scored:
        for main in index.categories(item.row.keyword):
            members[main].append(item)
    # Ready to sell butuh label Gold/Potential dan harga pembeli: hanya keyword itu yang harganya dibaca.
    needed = {s.row.keyword for main in costed if main in members for s in members[main]
              if s.eligible and s.label in ("Gold", "Potential")}
    fits = {}
    if needed:
        profiles = build_profiles(store, only=needed)
        fits = fits_for_store(store, cfg, [s for s in scored if s.row.keyword in profiles], profiles)

    summaries = {}
    for main, info in categories.items():
        items = members[main]
        searched = sum(statuses.get(s.row.keyword) in SEARCHED for s in items)
        volumes = [s for s in items if s.row.metrics.search_volume is not None]
        top = max(volumes, key=lambda s: (s.row.metrics.search_volume, s.row.keyword), default=None)
        eligible = [s for s in items if s.eligible]
        best = max(eligible, key=lambda s: s.score, default=None)
        summaries[main] = CategorySummary(
            info=info, keywords=len(items), searched=searched,
            status="not_researched" if not items else ("researched" if searched else "harvested_only"),
            most_searched=(top.row.keyword, top.row.metrics.search_volume) if top else None,
            gold=sum(s.label == "Gold" for s in eligible), potential=sum(s.label == "Potential" for s in eligible),
            best=(best.row.keyword, best.score, best.label) if best else None,
            ready=sum(fits[s.row.keyword].ready for s in items if s.row.keyword in fits) if main in costed else None,
            models=len(info.blueprints), in_my_products=main in mine, research=research_state(statuses, main),
            top=tuple(sorted(eligible, key=lambda s: (-s.score, s.row.keyword))[:TOP_KEYWORDS]))
    return summaries


_SORTS = {
    "best": lambda s: (-(s.gold + s.potential), -(s.best[1] if s.best else -1), s.keywords == 0, s.info.name),
    "searched": lambda s: (-(s.most_searched[1] if s.most_searched else -1), s.info.name),
    "products": lambda s: (-s.models, s.info.name),
    "name": lambda s: s.info.name.lower(),
}


def sort_summaries(summaries: Iterable[CategorySummary], sort: str) -> list[CategorySummary]:
    """Urutkan kategori; *Other* selalu terakhir."""
    key = _SORTS.get(sort, _SORTS["best"])
    items = list(summaries)
    return (sorted((s for s in items if s.info.main != OTHER), key=key)
            + [s for s in items if s.info.main == OTHER])


def provider_list(printify: PrintifyStore, client: Callable[[], PrintifyClient], blueprint_id: int,
                  now: datetime) -> list[tuple[int, str]]:
    """Print provider untuk sebuah model: dari cache (30 hari), atau dari Printify lalu disimpan."""
    cached = printify.cached_providers(blueprint_id, now)
    if cached is not None:
        return cached
    providers = [(item["id"], str(item.get("title") or "")) for item in client().providers(blueprint_id)
                 if isinstance(item, dict) and isinstance(item.get("id"), int)]
    printify.save_providers(blueprint_id, providers, now)
    return providers


def shipping_for(printify: PrintifyStore, client: Callable[[], PrintifyClient], blueprint_id: int,
                 provider_id: int, now: datetime) -> ShippingInfo:
    """Ongkir ke AS dan waktu produksi: dari cache (30 hari), atau dari Printify lalu disimpan."""
    cached = printify.cached_shipping(blueprint_id, provider_id, now)
    if cached is not None:
        return cached
    shipping = client().shipping(blueprint_id, provider_id)
    check_shipping(f"/v1/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/shipping.json", shipping)
    info = ShippingInfo(us_shipping_cents(shipping, None), handling_days(shipping))
    printify.save_shipping(blueprint_id, provider_id, info, now)
    return info
