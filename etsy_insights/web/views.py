"""Halaman web: Session, Opportunities, Keyword detail, My keywords, Settings."""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlencode

from flask import Blueprint, abort, current_app, render_template, request

from ..export import STATUS_TEXT
from ..keywords import list_user_keywords
from ..models import CONVERSION_LEVEL_TEXT
from ..score import ScoredKeyword, score_all
from ..settings import settings_form
from ..store import normalize_keyword
from ..taste import TasteProfile, build_profile, build_profiles
from . import get_config, get_store, home
from .api import status_payload

bp = Blueprint("views", __name__)
LABELS = ("Gold", "Potential", "Skip")
DIFFICULTIES = ("Easy", "Medium", "Hard", "Not searched yet")
PAGE_SIZE = 50
SORT_KEYS = {
    "score": lambda s: s.score or 0,
    "volume": lambda s: s.row.metrics.search_volume or 0,
    "competition": lambda s: s.row.metrics.competition_value or 0,
    "conversion": lambda s: s.row.metrics.conversion_level if s.row.metrics.conversion_level is not None else -1,
    "keyword": lambda s: s.row.keyword,
}
CONVERSION_CLASS = {0: "vlow", 1: "low", 2: "typical", 3: "high", 4: "vhigh"}


def trend_points(values: Sequence[float], width: int = 760, height: int = 200) -> str:
    """Titik polyline SVG; skala y 0..max*1.1."""
    if not values:
        return ""
    top = max(values) * 1.1 or 1
    step = width / (len(values) - 1) if len(values) > 1 else 0
    return " ".join(f"{i * step:.1f},{height - v / top * height:.1f}" for i, v in enumerate(values))


def _number(value) -> str:
    return "—" if value is None else f"{value:,.0f}".replace(",", ".")


def _range(low, high) -> str:
    return f"{low} – {high}" if low and high else ""


@dataclass(frozen=True)
class Row:
    keyword: str
    volume: str
    competition: str
    conversion: str
    conversion_class: str
    score: str
    label: str
    difficulty: str
    market_price: str
    wow: str


def _row(s: ScoredKeyword, profile: TasteProfile | None) -> Row:
    m = s.row.metrics
    level = m.conversion_level
    return Row(
        keyword=s.row.keyword, volume=_number(m.search_volume), competition=_number(m.competition_value),
        conversion=CONVERSION_LEVEL_TEXT.get(level, "—") if isinstance(level, int) else "—",
        conversion_class=CONVERSION_CLASS.get(level, "none") if isinstance(level, int) else "none",
        score=f"{s.score:.1f}" if s.score is not None else "—", label=s.label,
        difficulty=profile.difficulty if profile else "Not searched yet",
        market_price=_range(profile.paid_price_low, profile.paid_price_high) if profile else "",
        wow=f"{m.wow_pct:+.1f}%" if m.wow_pct is not None else "")


def _page(name: str, **context):
    return render_template(f"{name}.html", active=context.pop("active", name),
                           token=current_app.config["APP_TOKEN"], **context)


@bp.get("/")
def session_page():
    return _page("session", active="session", status=status_payload())


def _int_arg(name: str, default: int | None = None) -> int | None:
    try:
        return int(request.args.get(name, ""))
    except ValueError:
        return default


@bp.get("/opportunities")
def opportunities():
    store, cfg = get_store(), get_config()
    profiles = build_profiles(store)
    scored = [s for s in score_all(store.latest_results(), cfg) if s.eligible]
    labels = [v for v in request.args.getlist("label") if v in LABELS]
    difficulties = [v for v in request.args.getlist("difficulty") if v in DIFFICULTIES]
    conv_min = _int_arg("conv_min")
    vol_min = _int_arg("vol_min")
    query = normalize_keyword(request.args.get("q", ""))

    def keep(s: ScoredKeyword) -> bool:
        m, profile = s.row.metrics, profiles.get(s.row.keyword)
        difficulty = profile.difficulty if profile else "Not searched yet"
        return ((not labels or s.label in labels) and (not difficulties or difficulty in difficulties)
                and (conv_min is None or (m.conversion_level is not None and m.conversion_level >= conv_min))
                and (vol_min is None or (m.search_volume or 0) >= vol_min)
                and (not query or query in s.row.keyword))

    sort = request.args.get("sort", "score")
    sort = sort if sort in SORT_KEYS else "score"
    direction = request.args.get("dir", "asc" if sort == "keyword" else "desc")
    rows = sorted(filter(keep, scored), key=SORT_KEYS[sort], reverse=direction == "desc")
    pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = min(max(1, _int_arg("page", 1) or 1), pages)
    shown = [_row(s, profiles.get(s.row.keyword)) for s in rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]]

    def link(**changes) -> str:
        params = {"label": labels, "difficulty": difficulties, "conv_min": conv_min, "vol_min": vol_min,
                  "q": request.args.get("q", ""), "sort": sort, "dir": direction, "page": page}
        params.update(changes)
        return "/opportunities?" + urlencode({k: v for k, v in params.items() if v not in (None, "", [])},
                                             doseq=True)

    def sort_link(key: str) -> str:
        new_dir = "desc" if key != sort else ("asc" if direction == "desc" else "desc")
        return link(sort=key, dir=new_dir, page=1)

    page_links = [(n, link(page=n)) for n in range(1, pages + 1)]
    return _page("opportunities", rows=shown, total=len(rows), ranked=len(scored), labels=labels,
                 difficulties=difficulties, conv_min=conv_min, vol_min=vol_min, q=request.args.get("q", ""),
                 sort=sort, direction=direction, page=page, pages=pages, page_links=page_links,
                 sort_link=sort_link, all_labels=LABELS, all_difficulties=DIFFICULTIES,
                 conversion_levels=CONVERSION_LEVEL_TEXT)


@bp.get("/keyword/<path:keyword>")
def keyword_detail(keyword: str):
    store, cfg = get_store(), get_config()
    item = store.get(keyword)
    if item is None:
        abort(404)
    scored = next((s for s in score_all(store.latest_results(), cfg) if s.row.keyword_id == item.id), None)
    raw = store.latest_search_raw(item.id)
    profile = build_profile(raw) if raw is not None else None
    metrics = scored.row.metrics if scored else None
    children = []
    for child in store.harvested_from(item.id):
        level = child.metrics.conversion_level
        children.append({
            "keyword": child.keyword, "volume": _number(child.metrics.search_volume),
            "competition": _number(child.metrics.competition_value),
            "conversion": CONVERSION_LEVEL_TEXT.get(level, "—") if isinstance(level, int) else "—",
            "conversion_class": CONVERSION_CLASS.get(level, "none") if isinstance(level, int) else "none",
            "can_prioritize": child.status == "harvested"})
    per_listing = None
    if metrics and metrics.search_volume and metrics.competition_value:
        per_listing = f"{metrics.search_volume / metrics.competition_value:.3f}"
    return _page(
        "keyword", active="opportunities", item=item, scored=scored, metrics=metrics, profile=profile,
        status_text=STATUS_TEXT.get(item.status, item.status),
        volume=_number(metrics.search_volume) if metrics else "—",
        competition=_number(metrics.competition_value) if metrics else "—",
        conversion=(CONVERSION_LEVEL_TEXT.get(metrics.conversion_level, "—")
                    if metrics and isinstance(metrics.conversion_level, int) else "—"),
        conversion_class=(CONVERSION_CLASS.get(metrics.conversion_level, "none")
                          if metrics and isinstance(metrics.conversion_level, int) else "none"),
        wow=f"{metrics.wow_pct:+.1f}%" if metrics and metrics.wow_pct is not None else "—",
        per_listing=per_listing or "—",
        points=trend_points(metrics.trend) if metrics else "",
        paid=_range(profile.paid_price_low, profile.paid_price_high) if profile else "",
        listing_range=_range(profile.listing_price_low, profile.listing_price_high) if profile else "",
        children=children, can_prioritize=item.status == "harvested")


@bp.get("/keywords")
def keywords_page():
    entries = [{"keyword": k.keyword, "status": STATUS_TEXT.get(k.status, k.status), "removable": k.status == "pending"}
               for k in list_user_keywords(home(), get_store())]
    return _page("keywords", active="keywords", entries=entries)


@bp.get("/settings")
def settings_page():
    return _page("settings", active="settings", form=settings_form(get_config()))


LOG_LINES = 500


def latest_log(logs_dir) -> tuple[str | None, list[str]]:
    """(file name, last lines) of the newest session log or session output."""
    files = [p for pattern in ("*.log", "*.out") for p in logs_dir.glob(pattern)] if logs_dir.is_dir() else []
    if not files:
        return None, []
    newest = max(files, key=lambda p: p.stat().st_mtime)
    lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
    return newest.name, lines[-LOG_LINES:]


@bp.get("/log")
def log_page():
    file_name, lines = latest_log(home() / "logs")
    return _page("log", active="session", file_name=file_name, lines=lines)
