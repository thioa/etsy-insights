"""Halaman dan API Printify (spec Tahap 4 §10–§11). Token Printify tidak pernah dikirim ke browser."""
from __future__ import annotations

import secrets
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from ..keywords import add_keywords
from ..margin import money, parse_usd_cents
from ..printify_api import PrintifyError
from ..printify_store import PrintifyStore
from ..printify_suggestions import suggest
from ..printify_sync import NotConnected, SyncBusy, handling_days, us_shipping_cents
from ..printify_token import clean_token, delete_token, load_token, looks_like_token, save_token, token_hint
from ..product_fit import match_counts
from ..store import normalize_keyword
from . import ctx, get_store, home
from .views import _page

bp = Blueprint("printify", __name__)
COST_ERROR = "Enter an amount from 0.01 to 500."
MAX_COST_CENTS = 50000


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400):
    return jsonify(error=message), status


def _int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _cost_cents(text) -> int | None:
    """US$ dari formulir (misalnya "12.50") → sen, atau None kalau tidak valid."""
    cents = parse_usd_cents("$" + str(text).strip().lstrip("$")) if text is not None else None
    return cents if cents is not None and 1 <= cents <= MAX_COST_CENTS else None


def _local(text: str | None) -> str | None:
    return f"{datetime.fromisoformat(text).astimezone():%Y-%m-%d %H:%M}" if text else None


def _shops(shops: list) -> list[dict]:
    return [{"id": s.get("id"), "title": s.get("title"), "sales_channel": s.get("sales_channel")}
            for s in shops if isinstance(s, dict)]


def _client():
    token = load_token(home())
    if not token:
        raise NotConnected()
    return ctx().printify_client(token)


@bp.get("/printify")
def printify_page():
    store = get_store()
    printify = PrintifyStore(store)
    token = load_token(home())
    status = ctx().printify_job.status()
    types = printify.types()
    links = printify.links()
    counts = match_counts([r.keyword for r in store.latest_results()], types, links)
    rows = [{
        "id": t.id, "title": t.title, "provider": t.provider_title or "", "source": t.source,
        "source_text": "Your product" if t.source == "own" else "Picked", "words": ", ".join(t.words),
        "cost": money(t.cost_min_cents) if t.cost_min_cents is not None else "",
        "cost_input": f"{t.cost_min_cents / 100:.2f}" if t.cost_min_cents is not None else "",
        "shipping": money(t.shipping_us_cents) if t.shipping_us_cents is not None else "No US shipping",
        "matches": counts.get(t.id, 0), "available": t.available} for t in types]
    suggestions = suggest(types, printify.products(), store.keyword_texts())
    error = status.get("error") if status.get("state") in ("error", "idle") else None
    return _page("printify", active="printify", connected=bool(token), hint=token_hint(token) if token else "",
                 shop_title=printify.meta("shop_title"), last_sync=_local(printify.meta("last_sync_at")),
                 status=status, error=error, rows=rows, suggestions=suggestions,
                 has_catalog=printify.has_blueprints())


@bp.get("/api/printify/status")
def status():
    return jsonify(ctx().printify_job.status())


@bp.post("/api/printify/token")
def save():
    cleaned = clean_token(str(_body().get("token") or ""))
    if not cleaned:
        return _error("Paste your Printify token.")
    if not looks_like_token(cleaned):
        return _error("That does not look like a Printify token.")
    try:
        shops = ctx().printify_client(cleaned).shops()
    except PrintifyError as exc:
        return _error(exc.message)
    save_token(home(), cleaned)
    return jsonify(shops=_shops(shops))


@bp.post("/api/printify/test")
def test_connection():
    try:
        shops = _client().shops()
    except NotConnected as exc:
        return _error(exc.message, 409)
    except PrintifyError as exc:
        return _error(exc.message)
    return jsonify(shops=_shops(shops))


@bp.post("/api/printify/disconnect")
def disconnect():
    delete_token(home())
    return jsonify(ok=True)


@bp.post("/api/printify/shop")
def choose_shop():
    shop_id = _int(_body().get("shop_id"))
    if shop_id is None:
        return _error("Choose a shop.")
    PrintifyStore(get_store()).set_meta("shop_id", str(shop_id))
    try:  # langsung lanjutkan sync dengan toko yang dipilih
        ctx().printify_job.start()
    except (NotConnected, SyncBusy) as exc:
        return _error(exc.message, 409)
    return jsonify(ok=True), 202


@bp.post("/api/printify/sync")
def sync():
    try:
        ctx().printify_job.start()
    except (NotConnected, SyncBusy) as exc:
        return _error(exc.message, 409)
    return jsonify(ok=True), 202


@bp.get("/api/printify/catalog")
def catalog():
    printify = PrintifyStore(get_store())
    if not printify.has_blueprints():
        return _error("Run Sync once to search the catalog.", 409)
    results = printify.search_blueprints(request.args.get("q", ""))
    return jsonify(results=[{"id": b.id, "title": b.title, "brand": b.brand, "model": b.model} for b in results])


@bp.get("/api/printify/providers")
def providers():
    # Endpoint ini memakai token Printify Anda, jadi situs lain tidak boleh memanggilnya (wajib kode aplikasi).
    supplied = request.headers.get("X-App-Token", "")
    if not secrets.compare_digest(supplied, current_app.config["APP_TOKEN"]):
        return _error("Forbidden", 403)
    blueprint_id = _int(request.args.get("blueprint_id"))
    if blueprint_id is None:
        return _error("Choose a product.")
    try:
        items = _client().providers(blueprint_id)
    except NotConnected as exc:
        return _error(exc.message, 409)
    except PrintifyError as exc:
        return _error(exc.message)
    return jsonify(providers=[{"id": p.get("id"), "title": p.get("title")} for p in items if isinstance(p, dict)])


@bp.post("/api/printify/types/add")
def add_type():
    body = _body()
    blueprint_id, provider_id = _int(body.get("blueprint_id")), _int(body.get("print_provider_id"))
    if blueprint_id is None or provider_id is None:
        return _error("Choose a product and a print provider.")
    cost = None
    if str(body.get("cost_usd") or "").strip():
        cost = _cost_cents(body.get("cost_usd"))
        if cost is None:
            return _error(COST_ERROR)
    printify = PrintifyStore(get_store())
    blueprint = printify.blueprint(blueprint_id)
    if blueprint is None:
        return _error("Unknown product.", 404)
    try:
        client = _client()
        names = {p.get("id"): p.get("title") for p in client.providers(blueprint_id) if isinstance(p, dict)}
        if provider_id not in names:
            return _error("Unknown print provider.", 404)
        shipping = client.shipping(blueprint_id, provider_id)
    except NotConnected as exc:
        return _error(exc.message, 409)
    except PrintifyError as exc:
        return _error(exc.message)
    added = printify.add_picked(blueprint_id, provider_id, blueprint.title, names[provider_id], cost,
                                us_shipping_cents(shipping, None), handling_days(shipping), ctx().now())
    return jsonify(ok=True, type_id=added.id)


@bp.post("/api/printify/types/update")
def update_type():
    body = _body()
    type_id = _int(body.get("type_id"))
    printify = PrintifyStore(get_store())
    if type_id is None or printify.type(type_id) is None:
        return _error("Unknown product type.", 404)
    words = None
    if "words" in body:
        words = [w for w in str(body.get("words") or "").split(",")]
    cost = None
    if str(body.get("cost_usd") or "").strip():
        cost = _cost_cents(body.get("cost_usd"))
        if cost is None:
            return _error(COST_ERROR)
    try:
        printify.update_type(type_id, words=words, cost_cents=cost)
    except ValueError as exc:
        return _error(str(exc))
    return jsonify(ok=True)


@bp.post("/api/printify/types/remove")
def remove_type():
    type_id = _int(_body().get("type_id"))
    if type_id is None or not PrintifyStore(get_store()).remove_picked(type_id):
        return _error("Only picked product types can be removed.")
    return jsonify(ok=True)


@bp.post("/api/printify/link")
def link():
    body = _body()
    store = get_store()
    item = store.get(normalize_keyword(str(body.get("keyword") or "")))
    if item is None:
        return _error("Unknown keyword.", 404)
    printify = PrintifyStore(store)
    type_id = body.get("type_id")
    if type_id in (None, "", "auto"):
        printify.link(item.id, None)
        return jsonify(ok=True)
    type_id = _int(type_id)
    if type_id is None or printify.type(type_id) is None:
        return _error("Unknown product type.", 404)
    printify.link(item.id, type_id)
    return jsonify(ok=True)


@bp.post("/api/printify/suggestions/add")
def add_suggestions():
    keywords = _body().get("keywords")
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        return _error("Choose at least one keyword.")
    added = add_keywords(home(), get_store(), "\n".join(keywords), ctx().now())
    return jsonify(ok=True, added=added)
