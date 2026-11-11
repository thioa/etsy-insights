"""Halaman dan API AI Advisor (spec Tahap 6 §10). API key tidak pernah dikirim ke browser."""
from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, request

from ..advisor import AdvisorError, LimitReached
from ..advisor_ai import ClaudeBusy, ClaudeCertificateProblem, ClaudeError, ClaudeUnreachable
from ..advisor_brief import trend_pct
from ..advisor_key import BAD_KEY, clean_key, delete_key, key_hint, load_key, looks_like_key, save_key
from ..advisor_result import clean_idea, idea_status
from ..advisor_store import AdvisorStore, Report
from ..catalog import categories_from
from ..keywords import add_keywords
from ..margin import money
from ..models import CONVERSION_LEVEL_TEXT
from ..printify_store import PrintifyStore
from ..product_fit import fits_for_store, minimum_cents
from ..product_words import CATEGORY_NAMES, category_slug
from ..score import score_all
from ..taste import build_profiles
from . import ctx, get_config, get_store, home
from .printify import app_token_ok
from .views import CONVERSION_CLASS, _number, _page, margin_display

bp = Blueprint("advisor", __name__)
SAVED_UNTESTED = "Saved, but Anthropic could not be reached to test it."


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400):
    return jsonify(error=message), status


@bp.post("/api/advisor/key")
def save():
    key = clean_key(str(_body().get("key") or ""))
    if not key:
        return _error("Paste your Anthropic API key.")
    if not looks_like_key(key):
        return _error(BAD_KEY)
    try:
        ctx().advisor_client(key).test_key()
    except (ClaudeUnreachable, ClaudeCertificateProblem, ClaudeBusy):
        save_key(home(), key)
        return jsonify(hint=key_hint(key), warning=SAVED_UNTESTED)
    except ClaudeError as exc:
        return _error(exc.message)
    save_key(home(), key)
    return jsonify(hint=key_hint(key))


@bp.post("/api/advisor/disconnect")
def disconnect():
    delete_key(home())
    return jsonify(ok=True)


@bp.post("/api/advisor/run")
def run():
    try:
        report_id = ctx().advisor_job.start()
    except AdvisorError as exc:
        return _error(exc.message, exc.status)
    return jsonify(report_id=report_id), 202


@bp.get("/api/advisor/status")
def status():
    if not app_token_ok():
        return _error("Forbidden", 403)
    return jsonify(ctx().advisor_job.status())


@bp.post("/api/advisor/add")
def add():
    body = _body()
    keywords = body.get("keywords")
    if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) for k in keywords):
        return _error("Choose at least one keyword.")
    store = get_store()
    report_id = body.get("report_id")
    report = AdvisorStore(store).report(report_id) if isinstance(report_id, int) else None
    if report is None:
        return _error("Report not found.", 404)
    ideas = [i["keyword"] for i in (report.result or {}).get("keyword_ideas", [])]
    wanted = [k for k in dict.fromkeys(clean_idea(k) for k in keywords) if k in ideas]
    added = add_keywords(home(), store, "\n".join(wanted), ctx().now()) if wanted else []
    statuses = store.keyword_statuses()
    return jsonify(added=added, statuses={k: idea_status(k, statuses) for k in ideas})


# --- Halaman -------------------------------------------------------------------------------------------------------
KIND_TEXT = {"from_data": "From your data", "season": "Season", "trend": "Trend", "new_niche": "New niche"}
IDEA_STATUS_TEXT = {"new": "New", "in_queue": "In queue", "researched": "Researched"}
STAGE_TEXT = {None: "Starting…", "checking_trends": "Step 1 of 2 – Checking trends on the web…",
              "analyzing": "Step 2 of 2 – Analyzing your data…"}
REPORT_STATUS_TEXT = {"done": "Done", "error": "Failed", "interrupted": "Interrupted", "running": "Running"}


def _web_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _trend_text(value: float | None) -> str:
    return f"{value:+.1f}%" if value is not None else "—"


def _local(dt) -> str:
    return f"{dt.astimezone():%Y-%m-%d %H:%M}"


def report_view(report: Report, store, cfg) -> dict:
    """Laporan untuk template. Angka keyword selalu diambil dari database, bukan dari teks AI."""
    categories = categories_from(PrintifyStore(store).blueprints())
    result = report.result or {}
    recommendations = [r for r in result.get("recommendations", []) if isinstance(r, dict)]
    evidence = {k for r in recommendations for k in r.get("evidence", []) if isinstance(k, str)}
    scored = {s.row.keyword: s for s in score_all(store.latest_results(), cfg)} if evidence else {}
    found = [scored[k] for k in sorted(evidence) if k in scored]
    profiles = build_profiles(store, only=[s.row.keyword for s in found]) if found else {}
    fits = fits_for_store(store, cfg, [s for s in found if s.row.keyword in profiles], profiles) if found else {}
    minimum = minimum_cents(cfg)
    sources = {s.id: s for s in report.sources if _web_url(s.url)}

    def evidence_row(keyword: str) -> dict:
        item = scored.get(keyword)
        if item is None:
            return {"keyword": keyword, "found": False}
        m, level = item.row.metrics, item.row.metrics.conversion_level
        fit = fits.get(keyword)
        text, css, _ = margin_display(fit, minimum)
        return {"keyword": keyword, "found": True, "volume": _number(m.search_volume),
                "competition": _number(m.competition_value), "label": item.label,
                "conversion": CONVERSION_LEVEL_TEXT.get(level, "—") if isinstance(level, int) else "—",
                "conversion_class": CONVERSION_CLASS.get(level, "none") if isinstance(level, int) else "none",
                "trend": _trend_text(trend_pct(m.trend)), "margin_text": text, "margin_class": css,
                "ready": bool(fit and fit.ready)}

    def category(key: str) -> dict:
        info = categories.get(key)
        if info is None:
            return {"name": CATEGORY_NAMES.get(key, str(key).title()), "slug": None, "photo": ""}
        return {"name": info.name, "slug": category_slug(key), "photo": info.photo}

    statuses = store.keyword_statuses()
    ideas = []
    for idea in result.get("keyword_ideas", []):
        if not isinstance(idea, dict) or not isinstance(idea.get("keyword"), str):
            continue
        status = idea_status(idea["keyword"], statuses)
        ideas.append({"keyword": idea["keyword"], "category": category(idea.get("category"))["name"],
                      "kind": KIND_TEXT.get(idea.get("kind"), ""), "reason": idea.get("reason", ""),
                      "status": status, "status_text": IDEA_STATUS_TEXT[status]})
    return {
        "id": report.id, "status": report.status, "status_text": REPORT_STATUS_TEXT.get(report.status, report.status),
        "when": _local(report.started_at), "cost": money(report.usage.cost_cents), "error": report.error,
        "keywords": report.stats.get("keywords"), "categories": report.stats.get("categories"),
        "trend_failed": report.trend_failed, "trend_note": report.trend_note or "",
        "summary": result.get("summary", ""),
        "recommendations": [{
            "title": r.get("title", ""), "theme": r.get("theme", ""), "why": r.get("why", ""),
            "action": r.get("action", ""), "backed": bool(r.get("backed")), "category": category(r.get("category")),
            "evidence": [evidence_row(k) for k in r.get("evidence", []) if isinstance(k, str)],
            "sources": [sources[s] for s in r.get("sources", []) if s in sources]} for r in recommendations],
        "ideas": ideas, "sources": list(sources.values()),
    }


def _history(reports: list[Report]) -> list[dict]:
    return [{"id": r.id, "when": _local(r.started_at), "status_text": REPORT_STATUS_TEXT.get(r.status, r.status),
             "cost": money(r.usage.cost_cents), "ideas": len((r.result or {}).get("keyword_ideas", []))}
            for r in reports]


def _render(report: Report | None):
    store, cfg = get_store(), get_config()
    key = load_key(home())
    advisor = AdvisorStore(store)
    reports = advisor.reports()
    shown = report or next((r for r in reports if r.status != "running"), None)
    runs, spent = advisor.month_spend(ctx().now())
    limit = cfg.advisor_batas_bulanan_usd
    limit_message = LimitReached(limit).message if limit > 0 and spent >= round(limit * 100) else None
    counts = store.status_counts()
    status = ctx().advisor_job.status()
    has_catalog = PrintifyStore(store).has_blueprints()
    return _page(
        "advisor", active="advisor", connected=bool(key), hint=key_hint(key) if key else "",
        runs=runs, spent=money(spent), has_catalog=has_catalog, limit_message=limit_message,
        few_data=counts.get("done", 0) + counts.get("no_data", 0) < 20, status=status,
        stage_text=STAGE_TEXT.get(status.get("stage"), STAGE_TEXT[None]),
        can_run=bool(key) and has_catalog and limit_message is None and status["state"] != "running",
        view=report_view(shown, store, cfg) if shown else None, single=report is not None,
        history=_history(reports), daily_searches=cfg.kuota_harian,
        in_queue=counts.get("pending", 0) + counts.get("in_progress", 0))


@bp.get("/advisor")
def advisor_page():
    return _render(None)


@bp.get("/advisor/<int:report_id>")
def report_page(report_id: int):
    report = AdvisorStore(get_store()).report(report_id)
    if report is None:
        abort(404)
    return _render(report)
