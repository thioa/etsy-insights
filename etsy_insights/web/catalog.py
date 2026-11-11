"""Halaman dan API katalog Printify (spec Tahap 5 §6–§9)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..catalog import research, research_state, shipping_for
from ..margin import money
from ..printify_api import PrintifyError
from ..printify_store import PrintifyStore
from ..printify_sync import NotConnected
from ..product_words import ENTRIES, category_from_slug
from . import ctx, get_store, home
from .printify import _client, _error, _int, app_token_ok

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
