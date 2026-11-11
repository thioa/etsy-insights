"""Alur satu sesi: ambil keyword dari antrean, cari, simpan, jeda, berhenti dengan aman."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .config import Config
from .models import (BrowserClosed, DangerSignal, EtsyQuotaReached, InsightsPage, NotLoggedIn, PageLoadTimeout,
                     ParsedSearch, RawResult)
from .pacer import Pacer, cooldown_end, remaining_quota
from .planner import select_next, upcoming
from .store import Store

MAX_CONSECUTIVE_FAILURES = 3


class StopReason(str, Enum):
    QUOTA = "kuota_tercapai"
    DURATION = "durasi_habis"
    DANGER = "tanda_bahaya"
    FAILURES = "gagal_beruntun"
    INTERRUPTED = "dihentikan"
    BROWSER_CLOSED = "chrome_ditutup"
    QUEUE_EMPTY = "antrean_kosong"
    NOT_LOGGED_IN = "belum_login"
    COOLDOWN = "masa_pendinginan"
    NO_QUOTA = "kuota_habis"
    ETSY_QUOTA = "kuota_etsy"
    PAGE_UNAVAILABLE = "halaman_tidak_terbuka"


REASON_TEXT = {
    StopReason.QUOTA: "Daily limit reached.",
    StopReason.DURATION: "Session time limit reached.",
    StopReason.DANGER: "Etsy showed a warning (captcha, verification, sign-in or 403/429). Paused for 24 hours to protect your account.",
    StopReason.FAILURES: "3 failures in a row. Etsy's page may have changed — run Recording mode and send the file to Claude.",
    StopReason.INTERRUPTED: "Stopped by you.",
    StopReason.BROWSER_CLOSED: "Chrome was closed.",
    StopReason.QUEUE_EMPTY: "Nothing left to search. Add keywords in My keywords.",
    StopReason.NOT_LOGGED_IN: "Not signed in to Etsy in the 'Etsy Riset' Chrome window. Sign in there, then start again.",
    StopReason.COOLDOWN: "Cooldown is active.",
    StopReason.NO_QUOTA: "Today's searches are used up. Try again tomorrow.",
    StopReason.ETSY_QUOTA: "Etsy says the Marketplace Insights quota is (almost) used up. Try again tomorrow.",
    StopReason.PAGE_UNAVAILABLE: "Etsy's page didn't load (slow internet?). Try again later.",
}


@dataclass
class SessionDeps:
    store: Store
    page: InsightsPage
    parse: Callable[[RawResult], ParsedSearch]
    pacer: Pacer
    cfg: Config
    clock: Callable[[], datetime]
    sleep: Callable[[float], None]
    log: Callable[[str], None]
    parser_version: str


@dataclass(frozen=True)
class SessionSummary:
    stop_reason: StopReason
    checked: int
    succeeded: int
    no_data: int
    failed: int
    new_keywords: int
    queue_left: int
    quota_left: int
    cooldown_until: datetime | None
    danger: DangerSignal | None
    test_run: bool = False


@dataclass
class _State:
    checked: int = 0
    succeeded: int = 0
    no_data: int = 0
    failed: int = 0
    new_keywords: int = 0
    current_id: int | None = None
    session_id: int = 0
    tried: set[int] = field(default_factory=set)
    reason: StopReason | None = None
    test_run: bool = False
    cooldown_until: datetime | None = None
    danger: DangerSignal | None = None


def _summary(deps: SessionDeps, state: _State) -> SessionSummary:
    now = deps.clock()
    quota_left = remaining_quota(deps.cfg, deps.store.checked_on(now.date(), now.tzinfo))
    queue_left = len(upcoming(deps.store, deps.cfg, limit=10**9))
    return SessionSummary(state.reason, state.checked, state.succeeded, state.no_data, state.failed,
                          state.new_keywords, queue_left, quota_left,
                          state.cooldown_until, state.danger, state.test_run)


def _stop_for_danger(deps: SessionDeps, state: _State, danger: DangerSignal) -> None:
    state.reason = StopReason.DANGER
    state.danger = danger
    state.cooldown_until = cooldown_end(deps.clock(), deps.cfg)
    deps.log(f"Warning sign: {danger.kind} ({danger.detail}). Stopping.")


def _check_page(deps: SessionDeps, state: _State) -> bool:
    """Periksa tanda bahaya. True berarti sesi harus berhenti (alasan sudah diisi).

    Halaman yang tidak bisa diperiksa diperlakukan sebagai tanda bahaya (arah yang aman).
    """
    try:
        danger = deps.page.check_danger()
    except BrowserClosed:
        state.reason = StopReason.BROWSER_CLOSED
        return True
    except Exception as exc:
        danger = DangerSignal("verifikasi", f"Page could not be checked: {exc}")
    if danger is None:
        return False
    _stop_for_danger(deps, state, danger)
    return True


def _danger_or_closed(deps: SessionDeps, state: _State, keyword_id: int) -> bool:
    """Seperti _check_page, dan bila berhenti, keyword dikembalikan ke antrean."""
    if not _check_page(deps, state):
        return False
    deps.store.return_to_queue(keyword_id)
    state.current_id = None
    return True


def _loop(deps: SessionDeps, state: _State, limit: int, start: datetime, prev_end: datetime | None) -> None:
    store, page, pacer, cfg = deps.store, deps.page, deps.pacer, deps.cfg
    max_duration = timedelta(minutes=cfg.durasi_sesi_menit)
    streak = 0
    since_break = 0
    next_break = pacer.break_every()
    while True:
        if state.checked >= limit:
            state.reason = StopReason.QUOTA
            return
        if deps.clock() - start >= max_duration:
            state.reason = StopReason.DURATION
            return
        item = select_next(store, cfg, deps.clock(), state.tried)
        if item is None:
            state.reason = StopReason.QUEUE_EMPTY
            return
        if state.checked == 0 and prev_end is not None:
            wait = pacer.gap_seconds() - (deps.clock() - prev_end).total_seconds()
            if wait > 0:
                deps.log(f"Waiting {wait:.0f} seconds since the last session.")
                deps.sleep(wait)
                if deps.clock() - start >= max_duration:
                    state.reason = StopReason.DURATION
                    return
        if state.checked > 0:
            if since_break >= next_break:
                pause = pacer.break_seconds()
                deps.log(f"Break {pause:.0f} seconds.")
                deps.sleep(pause)
                since_break = 0
                next_break = pacer.break_every()
            else:
                deps.sleep(pacer.gap_seconds())
            if deps.clock() - start >= max_duration:
                state.reason = StopReason.DURATION
                return

        state.tried.add(item.id)
        store.mark_in_progress(item.id)
        state.current_id = item.id
        store.increment_checked(state.session_id)
        state.checked += 1
        since_break += 1
        deps.log(f"[{state.checked}/{limit}] {item.keyword}")

        try:
            raw = page.search(item.keyword)
        except PageLoadTimeout:
            if _danger_or_closed(deps, state, item.id):
                return
            store.record_failure(item.id)
            state.current_id = None
            state.failed += 1
            streak += 1
            deps.log(f"  page did not load: {item.keyword}")
        except BrowserClosed:
            store.return_to_queue(item.id)
            state.current_id = None
            state.reason = StopReason.BROWSER_CLOSED
            return
        else:
            if _danger_or_closed(deps, state, item.id):
                return
            try:
                parsed = deps.parse(raw)
            except EtsyQuotaReached as exc:
                store.return_to_queue(item.id)
                state.current_id = None
                state.reason = StopReason.ETSY_QUOTA
                deps.log(f"  Etsy quota used up: {exc.quota.remaining} of {exc.quota.total} left")
                return
            except Exception as exc:  # ParseError, atau parser crash karena data Etsy berubah
                store.record_failure(item.id)
                state.current_id = None
                state.failed += 1
                streak += 1
                deps.log(f"  could not read data: {exc}")
            else:
                now = deps.clock()
                store.save_result(item.id, parsed.main, raw, now, deps.parser_version)
                state.current_id = None
                streak = 0
                if parsed.main.has_data:
                    state.succeeded += 1
                else:
                    state.no_data += 1
                harvested = store.save_harvest(item.id, parsed.related, cfg.keyword_terkait_maks,
                                               cfg.kedalaman_maks, now)
                state.new_keywords += harvested
                deps.log(f"  {parsed.main.search_volume} searches, {len(parsed.related)} related keywords "
                         f"({harvested} new)")
                if parsed.quota is not None and parsed.quota.exhausted:
                    state.reason = StopReason.ETSY_QUOTA
                    deps.log(f"  Etsy quota: {parsed.quota.remaining} of {parsed.quota.total} left")
                    return
                try:
                    page.dwell(pacer.dwell_seconds(), pacer.should_scroll())
                except BrowserClosed:
                    state.reason = StopReason.BROWSER_CLOSED
                    return

        if streak >= MAX_CONSECUTIVE_FAILURES:
            state.reason = StopReason.FAILURES
            return


def run_session(deps: SessionDeps, max_keywords: int | None = None,
                ignore_cooldown: bool = False) -> SessionSummary:
    store, cfg = deps.store, deps.cfg
    state = _State(test_run=max_keywords is not None)
    now = deps.clock()
    recovered = store.recover_in_progress()
    if recovered:
        deps.log(f"{recovered} keywords from an interrupted session went back to the queue.")

    if not ignore_cooldown:
        cooldown = store.active_cooldown_until(now)
        if cooldown is not None:
            state.reason, state.cooldown_until = StopReason.COOLDOWN, cooldown
            return _summary(deps, state)
    limit = remaining_quota(cfg, store.checked_on(now.date(), now.tzinfo), max_keywords)
    if limit == 0:
        state.reason = StopReason.NO_QUOTA
        return _summary(deps, state)
    if StopReason.ETSY_QUOTA.value in store.stop_reasons_on(now.date(), now.tzinfo):
        state.reason = StopReason.ETSY_QUOTA
        return _summary(deps, state)

    prev = store.last_session()
    prev_end = (prev["ended_at"] or prev["started_at"]) if prev else None
    state.session_id = store.start_session(now)
    try:
        try:
            deps.page.open()
        except NotLoggedIn:
            state.reason = StopReason.NOT_LOGGED_IN
        except PageLoadTimeout:
            state.reason = StopReason.PAGE_UNAVAILABLE
        except BrowserClosed:
            state.reason = StopReason.BROWSER_CLOSED
        else:
            if not _check_page(deps, state):
                _loop(deps, state, limit, now, prev_end)
    except KeyboardInterrupt:
        state.reason = StopReason.INTERRUPTED
    except Exception:
        if state.current_id is not None:
            store.record_failure(state.current_id)
        store.end_session(state.session_id, deps.clock(), "error", None)
        raise
    if state.current_id is not None:
        store.return_to_queue(state.current_id)
    store.end_session(state.session_id, deps.clock(), state.reason.value, state.cooldown_until)
    deps.log(f"Stopped: {REASON_TEXT[state.reason]}")
    return _summary(deps, state)


def format_summary(summary: SessionSummary) -> str:
    reason = REASON_TEXT[summary.stop_reason]
    if summary.test_run and summary.stop_reason is StopReason.QUOTA:
        reason = f"Test run finished ({summary.checked} searches)."
    lines = [
        f"Session finished: {reason}",
        f"Keywords checked: {summary.checked} (ok {summary.succeeded}, no data {summary.no_data}, "
        f"failed {summary.failed})",
        f"New keywords found: {summary.new_keywords}",
        f"Queue left: {summary.queue_left}",
        f"Searches left today: {summary.quota_left}",
    ]
    if summary.danger is not None:
        lines.append(f"Warning: {summary.danger.kind} ({summary.danger.detail})")
    if summary.cooldown_until is not None:
        lines.append(f"Cooldown until: {summary.cooldown_until.astimezone():%Y-%m-%d %H:%M}")
    return "\n".join(lines)
