"""AI Advisor: pekerjaan latar satu-per-satu (spec Tahap 6 §4, §11). Pola sama dengan SyncJob Printify."""
from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .advisor_ai import MODEL, AdvisorAI, ClaudeError, KeyRejected, NoModelAccess, TrendResult, redact_key
from .advisor_brief import TAKEN_STATUSES, build_inputs
from .advisor_key import load_key
from .advisor_result import validate
from .advisor_store import AdvisorStore, Usage
from .config import load_config
from .printify_store import PrintifyStore
from .store import Store

log = logging.getLogger(__name__)
UNEXPECTED = "Something went wrong. See the log for details."


class AdvisorError(Exception):
    status = 400
    message = "Advice could not start."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class NotConnected(AdvisorError):
    message = "Connect Claude first."


class NoCatalog(AdvisorError):
    message = "Sync Printify first."


class LimitReached(AdvisorError):
    status = 403

    def __init__(self, limit_usd: float) -> None:
        super().__init__(f"You reached this month's Advisor limit (US${limit_usd:.2f}). Raise it in Settings or "
                         "wait until next month.")


class AdvisorBusy(AdvisorError):
    status = 409
    message = "Advice is already running."


def default_ai(key: str) -> AdvisorAI:
    return AdvisorAI(key)


def _thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="advisor", daemon=True).start()


class AdvisorJob:
    def __init__(self, home: Path, ai_factory: Callable[[str], AdvisorAI] = default_ai, *,
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
                 spawn: Callable[[Callable[[], None]], None] = _thread) -> None:
        self._home = Path(home)
        self._ai_factory = ai_factory
        self._now = now
        self._spawn = spawn
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"state": "idle", "stage": None, "report_id": None, "error": None,
                                       "started": None}
        if self._db_path().exists():  # analisis yang terputus karena aplikasi ditutup
            store = Store(self._db_path())
            try:
                AdvisorStore(store).mark_interrupted()
            finally:
                store.close()

    def _db_path(self) -> Path:
        return self._home / "data" / "etsy.db"

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._state.update(changes)

    def status(self) -> dict:
        with self._lock:
            state = dict(self._state)
        started = state.pop("started")
        state["elapsed_seconds"] = (int((self._now() - started).total_seconds())
                                    if started is not None and state["state"] == "running" else 0)
        return state

    def start(self) -> int:
        with self._lock:
            if self._state["state"] == "running":
                raise AdvisorBusy()
        if not load_key(self._home):
            raise NotConnected()
        cfg = load_config(self._home / "config.toml")[0]
        now = self._now()
        store = Store(self._db_path())
        try:
            if not PrintifyStore(store).has_blueprints():
                raise NoCatalog()
            advisor = AdvisorStore(store)
            limit = cfg.advisor_batas_bulanan_usd
            if limit > 0 and advisor.month_spend(now)[1] >= round(limit * 100):
                raise LimitReached(limit)
            with self._lock:
                if self._state["state"] == "running":
                    raise AdvisorBusy()
                report_id = advisor.start_report(now, MODEL)
                self._state.update(state="running", stage=None, report_id=report_id, error=None, started=now)
        finally:
            store.close()
        self._spawn(lambda: self.run_now(report_id))
        return report_id

    def _stage(self, advisor: AdvisorStore, report_id: int, stage: str) -> None:
        advisor.set_stage(report_id, stage)
        self._set(stage=stage)

    def run_now(self, report_id: int) -> None:
        store = Store(self._db_path())
        advisor = AdvisorStore(store)
        usage = Usage()
        trend: TrendResult | None = None
        trend_failed = False
        try:
            try:
                cfg = load_config(self._home / "config.toml")[0]
                trend_input, analysis_input = build_inputs(store, cfg, self._now())
                key = load_key(self._home)
                if not key:
                    raise ClaudeError(NotConnected.message)
                ai = self._ai_factory(key)
                self._stage(advisor, report_id, "checking_trends")
                try:
                    trend = ai.check_trends(trend_input)
                    usage += trend.usage
                except (KeyRejected, NoModelAccess):
                    raise
                except ClaudeError as exc:  # tren gagal: analisis tetap jalan dengan data saja
                    usage += exc.usage
                    trend_failed = True
                    log.warning("Advisor trend check failed: %s", redact_key(exc.message))
                self._stage(advisor, report_id, "analyzing")
                analysis = ai.analyze(analysis_input, trend)
                usage += analysis.usage
                statuses = store.keyword_statuses()
                with_data = ({k["keyword"] for k in analysis_input.payload["keywords"]}
                             | {r.keyword for r in store.latest_results() if r.metrics.has_data})
                validated = validate(analysis.data, categories=analysis_input.category_keys, with_data=with_data,
                                     taken={k for k, s in statuses.items() if s in TAKEN_STATUSES},
                                     source_ids={s.id for s in trend.sources} if trend else set())
                stats = {"keywords": analysis_input.keyword_count, "categories": analysis_input.category_count,
                         "dropped": validated.dropped}
                if any(validated.dropped.values()):
                    log.info("Advisor dropped from Claude's answer: %s", validated.dropped)
                advisor.finish_report(report_id, self._now(), trend_note=trend.note if trend else None,
                                      trend_failed=trend_failed, sources=trend.sources if trend else (),
                                      result=validated.result, stats=stats, usage=usage)
                self._set(state="done", stage=None, error=None)
            except ClaudeError as exc:
                usage += exc.usage
                self._fail(advisor, report_id, exc.message, usage, trend, trend_failed)
            except Exception:  # noqa: BLE001 - laporan selalu selesai dengan pesan yang bisa dibaca
                log.error("Advisor failed:\n%s", redact_key(traceback.format_exc()))
                self._fail(advisor, report_id, UNEXPECTED, usage, trend, trend_failed)
        finally:
            store.close()

    def _fail(self, advisor: AdvisorStore, report_id: int, message: str, usage: Usage, trend: TrendResult | None,
              trend_failed: bool) -> None:
        try:
            advisor.fail_report(report_id, self._now(), message, usage, trend_note=trend.note if trend else None,
                                trend_failed=trend_failed, sources=trend.sources if trend else ())
        except Exception:  # noqa: BLE001 - status tetap tampil di halaman
            log.error("Advisor could not save the failed report:\n%s", redact_key(traceback.format_exc()))
        self._set(state="error", stage=None, error=message)
