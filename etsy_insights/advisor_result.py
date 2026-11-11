"""Validasi dan pengayaan jawaban AI Advisor (spec Tahap 6 §6.4). Jawaban AI tidak pernah dipercaya mentah-mentah."""
from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .product_words import ENTRIES, matches
from .store import normalize_keyword

MAX_RECOMMENDATIONS = 8
MAX_IDEAS = 20
MAX_IDEA_WORDS = 6
MAX_IDEA_CHARS = 60
KINDS = ("from_data", "season", "trend", "new_niche")
LIMITS = {"title": 120, "theme": 120, "why": 600, "action": 600, "reason": 300, "summary": 1200}
_NOT_KEYWORD = re.compile(r"[^\w\s'&-]|_")


@dataclass(frozen=True)
class Validated:
    result: dict
    dropped: dict[str, int]


def clean_idea(text: str) -> str:
    """Keyword usulan seperti yang diketik pembeli: huruf kecil, tanpa tanda baca selain ' - &."""
    return normalize_keyword(_NOT_KEYWORD.sub(" ", str(text))).strip(" '-&")


def _text(value: object, limit: str) -> str:
    return (value if isinstance(value, str) else "").strip()[:LIMITS[limit]]


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def validate(raw: dict, *, categories: Collection[str], with_data: Collection[str], taken: Collection[str],
             source_ids: Collection[str]) -> Validated:
    categories, with_data, taken, source_ids = set(categories), set(with_data), set(taken), set(source_ids)
    dropped = {"recommendations": 0, "evidence": 0, "sources": 0, "ideas": 0}

    recommendations = []
    for item in raw.get("recommendations") or []:
        if not isinstance(item, dict) or item.get("category") not in categories:
            dropped["recommendations"] += 1
            continue
        if len(recommendations) >= MAX_RECOMMENDATIONS:
            dropped["recommendations"] += 1
            continue
        evidence: list[str] = []
        for keyword in _strings(item.get("evidence_keywords")):
            normal = normalize_keyword(keyword)
            if normal in with_data and normal not in evidence:
                evidence.append(normal)
            elif normal not in evidence:
                dropped["evidence"] += 1
        sources = []
        for source in _strings(item.get("sources")):
            if source in source_ids and source not in sources:
                sources.append(source)
            elif source not in sources:
                dropped["sources"] += 1
        recommendations.append({
            "title": _text(item.get("title"), "title"), "category": item["category"],
            "theme": _text(item.get("theme"), "theme"), "why": _text(item.get("why"), "why"),
            "evidence": evidence, "sources": sources, "action": _text(item.get("action"), "action"),
            "backed": bool(evidence)})

    ideas: list[dict] = []
    seen: set[str] = set()
    for item in raw.get("keyword_ideas") or []:
        keyword = clean_idea(item.get("keyword", "")) if isinstance(item, dict) else ""
        category = item.get("category") if isinstance(item, dict) else None
        ok = (keyword and len(keyword) <= MAX_IDEA_CHARS and len(keyword.split()) <= MAX_IDEA_WORDS
              and keyword not in taken and keyword not in seen and category in categories
              and item.get("kind") in KINDS and matches(keyword, ENTRIES.get(category, (category,)))
              and len(ideas) < MAX_IDEAS)
        if not ok:
            dropped["ideas"] += 1
            continue
        seen.add(keyword)
        ideas.append({"keyword": keyword, "category": category, "kind": item["kind"],
                      "reason": _text(item.get("reason"), "reason")})

    result = {"summary": _text(raw.get("summary"), "summary"), "recommendations": recommendations,
              "keyword_ideas": ideas}
    return Validated(result, dropped)


def idea_status(keyword: str, statuses: Mapping[str, str]) -> str:
    status = statuses.get(keyword)
    if status in ("pending", "in_progress"):
        return "in_queue"
    if status in ("done", "no_data"):
        return "researched"
    return "new"
