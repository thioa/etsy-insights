"""Profil selera pembeli per keyword, dari ±20 listing teratas di Marketplace Insights (spec §16.8).

Datanya sudah ada di respons `results-data` yang disimpan saat pencarian; tidak ada request tambahan.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .models import RawResult
from .parser import is_results_for

if TYPE_CHECKING:
    from .store import Store

STOPWORDS = {"and", "are", "for", "from", "the", "this", "with", "you", "your", "our", "its",
             "gift", "gifts", "custom", "personalized", "personalised", "handmade"}
EXAMPLE_COUNT = 5
_TOKEN_RE = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class ListingCard:
    title: str
    price_text: str
    price_value: float | None
    reviews: int | None
    bestseller: bool
    star_seller: bool
    shop: str
    url: str
    image_url: str = ""


@dataclass(frozen=True)
class TasteProfile:
    keyword: str
    listing_count: int
    top_terms: tuple[tuple[str, int], ...]
    paid_price_low: str | None
    paid_price_high: str | None
    listing_price_low: str | None
    listing_price_high: str | None
    median_reviews: int | None
    bestseller_share: float
    star_seller_share: float
    unique_shops: int
    difficulty: str  # "Easy" | "Medium" | "Hard" | "Unknown"
    examples: tuple[ListingCard, ...]


def parse_price(text: str | None) -> float | None:
    """'Rp 712,738' -> 712738.0 ; 'US$15.30' -> 15.3 (koma = pemisah ribuan)."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text).replace(",", "")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def top_terms(titles: Sequence[str], keyword: str, limit: int = 10) -> list[tuple[str, int]]:
    """Kata & frasa dua kata yang muncul di >= 2 judul (dihitung per judul)."""
    own = set(_TOKEN_RE.findall(keyword.lower()))
    excluded = STOPWORDS | own | {word + "s" for word in own}
    counts: Counter[str] = Counter()
    for title in titles:
        tokens = [t for t in _TOKEN_RE.findall(title.lower()) if len(t) >= 3 and t not in excluded]
        counts.update(set(tokens) | {f"{a} {b}" for a, b in zip(tokens, tokens[1:])})
    candidates = sorted(((term, n) for term, n in counts.items() if n >= 2),
                        key=lambda item: (-item[1], -item[0].count(" "), item[0]))
    phrases = [(term, n) for term, n in candidates if " " in term]
    result = [(term, n) for term, n in candidates
              if " " in term or not any(n == pn and term in phrase.split() for phrase, pn in phrases)]
    return result[:limit]


def difficulty(median_reviews: int | None, bestseller_share: float, star_seller_share: float) -> str:
    if median_reviews is None:
        return "Unknown"
    if median_reviews >= 2000 or (bestseller_share >= 0.8 and median_reviews >= 1000):
        return "Hard"
    if median_reviews < 300 and bestseller_share < 0.5:
        return "Easy"
    return "Medium"


def _reviews(value: Any) -> int | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    return int(text) if text.isdigit() else None


def _card(data: Any) -> ListingCard | None:
    if not isinstance(data, dict) or not isinstance(data.get("title"), str):
        return None
    price = data.get("price") if isinstance(data.get("price"), dict) else {}
    price_text = str(price.get("formattedPrice") or "")
    return ListingCard(title=data["title"], price_text=price_text, price_value=parse_price(price_text),
                       reviews=_reviews(data.get("numberOfReviews")), bestseller=data.get("badgeText") == "Bestseller",
                       star_seller=bool(data.get("isStarSeller")), shop=str(data.get("shopName") or ""),
                       url=str(data.get("listingUrl") or ""), image_url=str(data.get("imageUrl") or ""))


def build_profile(raw: RawResult) -> TasteProfile | None:
    results = [r for r in raw.responses if is_results_for(r, raw.keyword)]
    if not results:
        return None
    body = results[-1].body
    research = body.get("competitiveResearchListingCards")
    cards_data = research.get("listingCards") if isinstance(research, dict) else None
    cards = [card for card in (_card(c) for c in cards_data or []) if card is not None]
    if not cards:
        return None
    reviews = [c.reviews for c in cards if c.reviews is not None]
    median_reviews = int(statistics.median(reviews)) if reviews else None
    priced = [c for c in cards if c.price_value is not None]
    price_data = body.get("competitivePriceData") if isinstance(body.get("competitivePriceData"), dict) else {}
    paid = price_data.get("searchTermMedianPrice") if isinstance(price_data.get("searchTermMedianPrice"), dict) else {}
    bestseller_share = sum(c.bestseller for c in cards) / len(cards)
    star_seller_share = sum(c.star_seller for c in cards) / len(cards)
    return TasteProfile(
        keyword=raw.keyword, listing_count=len(cards),
        top_terms=tuple(top_terms([c.title for c in cards], raw.keyword)),
        paid_price_low=paid.get("medianPriceLow"), paid_price_high=paid.get("medianPriceHigh"),
        listing_price_low=min(priced, key=lambda c: c.price_value).price_text if priced else None,
        listing_price_high=max(priced, key=lambda c: c.price_value).price_text if priced else None,
        median_reviews=median_reviews, bestseller_share=bestseller_share, star_seller_share=star_seller_share,
        unique_shops=len({c.shop for c in cards}),
        difficulty=difficulty(median_reviews, bestseller_share, star_seller_share),
        examples=tuple(cards[:EXAMPLE_COUNT]))


def build_profiles(store: Store) -> dict[str, TasteProfile]:
    profiles = {}
    for raw in store.latest_search_raws().values():
        profile = build_profile(raw)
        if profile is not None:
            profiles[raw.keyword] = profile
    return profiles
