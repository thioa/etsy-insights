"""Halaman dan API AI Advisor (spec Tahap 6 §10). API key tidak pernah dikirim ke browser."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..advisor import AdvisorError
from ..advisor_ai import ClaudeBusy, ClaudeCertificateProblem, ClaudeError, ClaudeUnreachable
from ..advisor_key import BAD_KEY, clean_key, delete_key, key_hint, looks_like_key, save_key
from ..advisor_result import clean_idea, idea_status
from ..advisor_store import AdvisorStore
from ..keywords import add_keywords
from . import ctx, get_store, home
from .printify import app_token_ok

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
