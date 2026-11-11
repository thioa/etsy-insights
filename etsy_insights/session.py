"""Alur satu sesi: ambil keyword dari antrean, cari, simpan, jeda, berhenti dengan aman."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .config import Config
from .models import (BrowserClosed, DangerSignal, InsightsPage, NotLoggedIn, PageLoadTimeout, ParsedSearch,
                     RawResult)
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
    StopReason.QUOTA: "Kuota untuk sesi/hari ini sudah tercapai.",
    StopReason.DURATION: "Batas durasi sesi sudah tercapai.",
    StopReason.DANGER: "Etsy menampilkan tanda bahaya (CAPTCHA/verifikasi/login/403/429). Sesi dihentikan demi keamanan akun.",
    StopReason.FAILURES: "3 kegagalan berturut-turut. Kemungkinan tampilan Etsy berubah: jalankan kenali.command lagi.",
    StopReason.INTERRUPTED: "Sesi dihentikan oleh Anda.",
    StopReason.BROWSER_CLOSED: "Chrome ditutup saat sesi berjalan.",
    StopReason.QUEUE_EMPTY: "Antrean keyword sudah habis. Tambahkan keyword di keywords.txt.",
    StopReason.NOT_LOGGED_IN: "Chrome 'Etsy Riset' belum login ke Etsy. Silakan login manual dulu.",
    StopReason.COOLDOWN: "Masih dalam masa pendinginan setelah tanda bahaya sebelumnya.",
    StopReason.NO_QUOTA: "Kuota hari ini sudah habis. Coba lagi besok.",
    StopReason.ETSY_QUOTA: "Etsy menandai kuota Marketplace Insights hampir/sudah habis. Coba lagi besok.",
    StopReason.PAGE_UNAVAILABLE: "Halaman Etsy tidak bisa dibuka (internet lambat?). Coba lagi nanti.",
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
    cooldown_until: datetime | None = None
    danger: DangerSignal | None = None


def _summary(deps: SessionDeps, state: _State) -> SessionSummary:
    now = deps.clock()
    quota_left = remaining_quota(deps.cfg, deps.store.checked_on(now.date(), now.tzinfo))
    queue_left = len(upcoming(deps.store, deps.cfg, limit=10**9))
    return SessionSummary(state.reason, state.checked, state.succeeded, state.no_data, state.failed,
                          state.new_keywords, queue_left, quota_left,
                          state.cooldown_until, state.danger)


def _stop_for_danger(deps: SessionDeps, state: _State, danger: DangerSignal) -> None:
    state.reason = StopReason.DANGER
    state.danger = danger
    state.cooldown_until = cooldown_end(deps.clock(), deps.cfg)
    deps.log(f"Tanda bahaya: {danger.kind} ({danger.detail}). Berhenti.")


def _danger_or_closed(deps: SessionDeps, state: _State, keyword_id: int) -> bool:
    """Periksa tanda bahaya. True berarti sesi harus berhenti (keyword sudah dikembalikan ke antrean)."""
    try:
        danger = deps.page.check_danger()
    except BrowserClosed:
        danger, state.reason = None, StopReason.BROWSER_CLOSED
    if danger is None and state.reason is None:
        return False
    deps.store.return_to_queue(keyword_id)
    state.current_id = None
    if danger is not None:
        _stop_for_danger(deps, state, danger)
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
                deps.log(f"Menunggu {wait:.0f} detik sejak sesi sebelumnya.")
                deps.sleep(wait)
                if deps.clock() - start >= max_duration:
                    state.reason = StopReason.DURATION
                    return
        if state.checked > 0:
            if since_break >= next_break:
                pause = pacer.break_seconds()
                deps.log(f"Istirahat {pause:.0f} detik.")
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
            deps.log(f"  halaman tidak termuat: {item.keyword}")
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
            except Exception as exc:  # ParseError, atau parser crash karena data Etsy berubah
                store.record_failure(item.id)
                state.current_id = None
                state.failed += 1
                streak += 1
                deps.log(f"  data tidak terbaca: {exc}")
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
                deps.log(f"  {parsed.main.search_volume} pencarian, {len(parsed.related)} keyword terkait "
                         f"({harvested} baru)")
                if parsed.quota is not None and parsed.quota.exhausted:
                    state.reason = StopReason.ETSY_QUOTA
                    deps.log(f"  kuota Etsy: sisa {parsed.quota.remaining} dari {parsed.quota.total}")
                    return
                page.dwell(pacer.dwell_seconds(), pacer.should_scroll())

        if streak >= MAX_CONSECUTIVE_FAILURES:
            state.reason = StopReason.FAILURES
            return


def run_session(deps: SessionDeps, max_keywords: int | None = None,
                ignore_cooldown: bool = False) -> SessionSummary:
    store, cfg = deps.store, deps.cfg
    state = _State()
    now = deps.clock()
    recovered = store.recover_in_progress()
    if recovered:
        deps.log(f"{recovered} keyword dari sesi yang terputus dikembalikan ke antrean.")

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
            danger = deps.page.check_danger()
            if danger is not None:
                _stop_for_danger(deps, state, danger)
            else:
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
    deps.log(f"Berhenti: {REASON_TEXT[state.reason]}")
    return _summary(deps, state)


def format_summary(summary: SessionSummary) -> str:
    lines = [
        f"Sesi selesai: {REASON_TEXT[summary.stop_reason]}",
        f"Keyword dicek: {summary.checked} (berhasil {summary.succeeded}, tanpa data {summary.no_data}, "
        f"gagal {summary.failed})",
        f"Keyword baru ditemukan: {summary.new_keywords}",
        f"Sisa antrean: {summary.queue_left}",
        f"Sisa kuota hari ini: {summary.quota_left}",
    ]
    if summary.danger is not None:
        lines.append(f"Tanda bahaya: {summary.danger.kind} ({summary.danger.detail})")
    if summary.cooldown_until is not None:
        lines.append(f"Masa pendinginan sampai: {summary.cooldown_until.astimezone():%Y-%m-%d %H:%M}")
    return "\n".join(lines)
