"""Halaman dan API katalog Printify (spec Tahap 5 §6–§9)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..catalog import categories_from, research, research_state, shipping_for, sort_summaries, summarize
from ..margin import money
from ..models import CONVERSION_LEVEL_TEXT
from ..printify_api import PrintifyError
from ..printify_store import PrintifyStore
from ..printify_sync import NotConnected
from ..product_fit import fits_for_store, minimum_cents
from ..product_words import ENTRIES, category_from_slug, normalize_words
from ..taste import build_profiles
from . import ctx, get_config, get_store, home
from .printify import _client, _error, _int, app_token_ok
from .views import CONVERSION_CLASS, _number, _page, margin_display

bp = Blueprint("catalog", __name__)


def _category(value) -> str | None:
    """Kata utama dari kata utama atau slug; None untuk "other" dan yang tidak dikenal."""
    text = str(value or "").strip().lower()
    main = text if text in ENTRIES else category_from_slug(text)
    return main if main in ENTRIES else None


@bp.post("/api/catalog/research")
def research_api():
    body = request.get_json(silent=True)
    main = _category(body.get("category") if isinstance(body, dict) else None)
    if main is None:
        return _error("Unknown category.", 404)
    store = get_store()
    state = research_state(store.keyword_statuses(), main)
    if state.status == "researched":
        return _error("Already researched.", 409)
    if state.status == "in_queue":
        return _error("Already in the research queue.", 409)
    return jsonify(added=research(home(), store, main, ctx().now()))


@bp.get("/api/catalog/shipping")
def shipping_api():
    if not app_token_ok():
        return _error("Forbidden", 403)
    blueprint_id, provider_id = _int(request.args.get("blueprint_id")), _int(request.args.get("provider_id"))
    if blueprint_id is None or provider_id is None:
        return _error("Choose a product and a print provider.")
    try:
        info = shipping_for(PrintifyStore(get_store()), _client, blueprint_id, provider_id, ctx().now())
    except NotConnected as exc:
        return _error(exc.message, 409)
    except PrintifyError as exc:
        return _error(exc.message)
    return jsonify(shipping_us_cents=info.shipping_us_cents, handling_days=info.handling_days,
                   shipping_text=money(info.shipping_us_cents) if info.shipping_us_cents is not None
                   else "No US shipping")


# --- halaman -------------------------------------------------------------------
SORTS = (("best", "Best opportunities"), ("searched", "Most searched"), ("products", "Most products"),
         ("name", "Name"))
STATUS_TEXT = {"not_researched": "Not researched yet", "harvested_only": "Harvested only", "researched": "Researched"}


def _searchable(summary) -> str:
    info = summary.info
    parts = [info.name, info.main] + [f"{b.title} {b.brand} {b.model}" for b in info.blueprints]
    return " ".join(normalize_words(" ".join(parts)))


def _summaries():
    store = get_store()
    blueprints = PrintifyStore(store).blueprints()
    if not blueprints:
        return blueprints, {}
    return blueprints, summarize(store, get_config(), categories_from(blueprints))


@bp.get("/catalog")
def catalog_page():
    blueprints, summaries = _summaries()
    if not blueprints:
        return _page("catalog", active="catalog", has_catalog=False)
    q = request.args.get("q", "")
    query = " ".join(normalize_words(q))
    sort = request.args.get("sort", "best")
    sort = sort if sort in dict(SORTS) else "best"
    status = request.args.get("status", "")
    status = status if status in ("researched", "not_researched") else ""
    mine = request.args.get("mine") == "1"

    def keep(summary) -> bool:
        return ((not query or query in _searchable(summary)) and (not status or summary.status == status)
                and (not mine or summary.in_my_products))

    cards = sort_summaries([s for s in summaries.values() if keep(s)], sort)
    return _page("catalog", active="catalog", has_catalog=True, cards=cards, q=q, sort=sort, status=status,
                 mine=mine, sorts=SORTS, status_text=STATUS_TEXT, number=_number,
                 no_photos=not any(b.image_url for b in blueprints), total_models=len(blueprints))


@bp.get("/catalog/<slug>")
def category_page(slug: str):
    blueprints, summaries = _summaries()
    main = category_from_slug(slug)
    if main is None or main not in summaries:
        return _page("unknown_category", active="catalog"), 404
    store, cfg = get_store(), get_config()
    summary = summaries[main]
    top = list(summary.top)
    profiles = build_profiles(store, only=[item.row.keyword for item in top])
    fits = fits_for_store(store, cfg, top, profiles)
    minimum = minimum_cents(cfg)
    rows = []
    for item in top:
        m, level = item.row.metrics, item.row.metrics.conversion_level
        text, css, _ = margin_display(fits.get(item.row.keyword), minimum)
        rows.append({"keyword": item.row.keyword, "volume": _number(m.search_volume),
                     "competition": _number(m.competition_value), "label": item.label,
                     "conversion": CONVERSION_LEVEL_TEXT.get(level, "—") if isinstance(level, int) else "—",
                     "conversion_class": CONVERSION_CLASS.get(level, "none") if isinstance(level, int) else "none",
                     "margin_text": text, "margin_class": css})
    mine_ids = {t.blueprint_id for t in PrintifyStore(store).types() if t.available}
    return _page("category", active="catalog", s=summary, rows=rows, mine_ids=mine_ids,
                 status_text=STATUS_TEXT, number=_number)
