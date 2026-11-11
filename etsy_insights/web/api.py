"""API JSON untuk halaman web (status sesi, mulai/berhenti, keyword, pengaturan, keluar)."""
from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request, send_file

from ..export import export_excel
from ..keywords import add_keywords, prioritize, remove_keyword
from ..pacer import remaining_quota
from ..paths import excel_dir
from ..planner import harvest_queue_size, upcoming
from ..runner import RunnerBusy
from ..score import score_all
from ..session import REASON_TEXT, StopReason, precheck, reason_text
from ..settings import save_settings
from ..taste import build_profiles
from . import ctx, get_config, get_store, home

bp = Blueprint("api", __name__)
TEST_RUN_SEARCHES = 3


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _blocker_text(reason: StopReason, until) -> str:
    if reason is StopReason.COOLDOWN and until is not None:
        return f"Cooldown is active until {until.astimezone():%Y-%m-%d %H:%M}."
    return REASON_TEXT[reason]


def account_state(store, now) -> dict:
    until = store.active_cooldown_until(now)
    if until is not None:
        return {"state": "cooldown", "until": until.isoformat(),
                "message": f"Paused until {until.astimezone():%Y-%m-%d %H:%M}"}
    if StopReason.ETSY_QUOTA.value in store.stop_reasons_on(now.date(), now.tzinfo):
        return {"state": "etsy_quota", "until": None, "message": REASON_TEXT[StopReason.ETSY_QUOTA]}
    return {"state": "safe", "until": None, "message": "Safe — no cooldown"}


def _harvest_queue_size(store, cfg) -> int:
    """harvest_queue_size, recomputed only after the database or settings changed (status is polled)."""
    cache = ctx().cache
    key = (store.change_stamp(), cfg)
    if cache.get("harvest_key") != key:
        cache["harvest_size"] = harvest_queue_size(store, cfg)
        cache["harvest_key"] = key
    return cache["harvest_size"]


def status_payload() -> dict:
    store, cfg, now = get_store(), get_config(), ctx().now()
    runner = ctx().runner.status()
    counts = store.status_counts()
    checked = store.checked_on(now.date(), now.tzinfo)
    pending = counts.get("pending", 0)
    harvest = _harvest_queue_size(store, cfg)
    reason, until = precheck(store, cfg, now, has_next=lambda: pending > 0 or harvest > 0 or store.next_recheck(
        now, cfg.cek_ulang_setelah_hari) is not None)
    last = store.last_session()
    return {
        "runner": asdict(runner) | {"log_tail": list(runner.log_tail), "error_tail": list(runner.error_tail)},
        "today": {"searches": checked, "limit": cfg.kuota_harian, "left": remaining_quota(cfg, checked)},
        "collected": sum(counts.get(k, 0) for k in ("done", "no_data", "harvested")),
        "queue": pending + harvest,
        "account": account_state(store, now),
        "last_session": None if last is None else {
            "started_at": last["started_at"].isoformat(),
            "started_text": f"{last['started_at'].astimezone():%Y-%m-%d %H:%M}", "checked": last["checked_count"],
            "reason_code": last["stop_reason"], "reason_text": reason_text(last["stop_reason"])},
        "can_start": not runner.running and reason is None,
        "blocker": None if reason is None else _blocker_text(reason, until),
    }


@bp.get("/api/ping")
def ping():
    return jsonify(ok=True, app="etsy-insights")


@bp.get("/api/status")
def status():
    return jsonify(status_payload())


@bp.post("/api/session/start")
def start():
    body = _body()
    test_run = bool(body.get("test_run"))
    ignore = bool(body.get("ignore_cooldown")) and body.get("confirm") == "YES"
    store, cfg, now = get_store(), get_config(), ctx().now()
    reason, until = precheck(store, cfg, now, TEST_RUN_SEARCHES if test_run else None, ignore_cooldown=ignore)
    if reason is not None:
        return jsonify(error=_blocker_text(reason, until)), 409
    try:
        ctx().runner.start(test_run=test_run, ignore_cooldown=ignore)
    except RunnerBusy as exc:
        return jsonify(error=str(exc)), 409
    return jsonify(ok=True)


@bp.post("/api/session/stop")
def stop():
    return jsonify(ok=ctx().runner.stop())


@bp.post("/api/keywords/add")
def keywords_add():
    added = add_keywords(home(), get_store(), str(_body().get("text", "")), ctx().now())
    return jsonify(added=added)


@bp.post("/api/keywords/remove")
def keywords_remove():
    if not remove_keyword(home(), get_store(), str(_body().get("keyword", ""))):
        return jsonify(error="Only queued keywords from your list can be removed."), 409
    return jsonify(ok=True)


@bp.post("/api/keywords/prioritize")
def keywords_prioritize():
    if not prioritize(home(), get_store(), str(_body().get("keyword", "")), ctx().now()):
        return jsonify(error="Unknown keyword."), 404
    return jsonify(ok=True)


@bp.post("/api/settings")
def settings():
    form = {k: str(v) for k, v in _body().items() if k != "token"}
    cfg, errors = save_settings(home(), form)
    if errors:
        return jsonify(errors=errors), 400
    return jsonify(ok=True)


@bp.post("/api/quit")
def quit_app():
    runner = ctx().runner
    state = runner.status()
    if state.running and state.source == "app":
        if _body().get("confirm") is not True:
            return jsonify(error="A session is running. Stop it and quit?"), 409
        runner.stop()
    ctx().on_quit()
    return jsonify(ok=True)


@bp.get("/download/excel")
def download_excel():
    store, cfg, now = get_store(), get_config(), ctx().now()
    path = export_excel(score_all(store.latest_results(), cfg), store.all_results(), upcoming(store, cfg),
                        excel_dir(home()), now.date(), profiles=build_profiles(store))
    return send_file(path, as_attachment=True, download_name=path.name)
