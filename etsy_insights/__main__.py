"""Perintah: python -m etsy_insights {run|status|export|kenali}"""
from __future__ import annotations

import argparse
import fcntl
import random
import signal
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from .browser import ChromeNotFound, ChromeStartTimeout, PortBusy, connected_browser, ensure_chrome
from .config import Config, ConfigError, load_config
from .export import export_excel
from .insights_page import EtsyInsightsPage
from .models import InsightsPage
from .pacer import Pacer, remaining_quota
from .paths import app_home, excel_dir
from .parser import PARSER_VERSION, parse_search
from .planner import upcoming
from .recorder import run_kenali
from .score import score_all
from .session import REASON_TEXT, SessionDeps, StopReason, format_summary, run_session
from .store import Store, read_keywords_file
from .taste import build_profiles

UJI_SEARCHES = 3


def _open_store(base: Path, now: datetime) -> Store:
    store = Store(base / "data" / "etsy.db")
    store.sync_user_keywords(read_keywords_file(base / "keywords.txt"), now)
    return store


def _reason_text(code: str | None) -> str:
    if code is None:
        return "not finished"
    if code == "error":
        return "The session stopped because of an unexpected error. See the log."
    try:
        return REASON_TEXT[StopReason(code)]
    except ValueError:
        return code


@contextmanager
def session_lock(path: Path) -> Iterator[bool]:
    """Kunci agar hanya satu sesi berjalan. Menghasilkan False bila sesi lain memegang kunci."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def interrupt_on_signals() -> Iterator[None]:
    """Menutup jendela Terminal (SIGHUP) atau SIGTERM diperlakukan seperti Ctrl+C."""
    def handler(signum, frame):
        raise KeyboardInterrupt
    previous = {sig: signal.signal(sig, handler) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        yield
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)


@contextmanager
def _open_insights(cfg: Config, pacer: Pacer, rng: random.Random, log) -> Iterator[InsightsPage]:
    endpoint = ensure_chrome(cfg.port_debug)
    with connected_browser(endpoint) as context:
        page = EtsyInsightsPage(context, pacer, rng, log=log)
        try:
            yield page
        finally:
            page.close()


def _status(base: Path, cfg: Config, now: datetime) -> int:
    store = _open_store(base, now)
    counts = store.status_counts()
    checked = store.checked_on(now.date(), now.tzinfo)
    print(f"Queue: {counts.get('pending', 0)} queued, {counts.get('harvested', 0)} harvested, "
          f"{counts.get('done', 0)} searched, {counts.get('no_data', 0)} no data, "
          f"{counts.get('failed', 0)} failed")
    print(f"Today: {checked}/{cfg.kuota_harian} searches (left {remaining_quota(cfg, checked)})")
    cooldown = store.active_cooldown_until(now)
    if cooldown is not None:
        print(f"Cooldown until: {cooldown.astimezone():%Y-%m-%d %H:%M}")
    last = store.last_session()
    if last is not None:
        print(f"Last session: {last['started_at'].astimezone():%Y-%m-%d %H:%M}, "
              f"{last['checked_count']} keywords. {_reason_text(last['stop_reason'])}")
    store.close()
    return 0


def _export(base: Path, cfg: Config, now: datetime) -> int:
    store = _open_store(base, now)
    path = export_excel(score_all(store.latest_results(), cfg), store.all_results(), upcoming(store, cfg),
                        excel_dir(base), now.date(), profiles=build_profiles(store))
    store.close()
    print(f"Excel file: {path}")
    return 0


def _kenali(base: Path, cfg: Config, now_fn: Callable[[], datetime]) -> int:
    endpoint = ensure_chrome(cfg.port_debug)
    with connected_browser(endpoint) as context:
        run_kenali(context, base / "rekaman", now_fn)
    return 0


def _make_logger(base: Path, now: datetime, log_file: Path | None = None) -> Callable[[str], None]:
    path = Path(log_file) if log_file else base / "logs" / f"sesi-{now:%Y%m%d-%H%M%S}.log"
    path.parent.mkdir(parents=True, exist_ok=True)

    def log(message: str) -> None:
        print(message)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%H:%M:%S} {message}\n")
    return log


def _run(base: Path, cfg: Config, now_fn: Callable[[], datetime], uji: bool, ignore_cooldown: bool,
         input_fn: Callable[[str], str], *, assume_yes: bool = False, log_file: Path | None = None) -> int:
    store = _open_store(base, now_fn())
    try:
        with session_lock(base / "data" / "sesi.lock") as locked:
            if not locked:
                print("Another session is running. Wait until it finishes.")
                return 1
            cooldown = store.active_cooldown_until(now_fn())
            if ignore_cooldown and cooldown is not None:
                print(f"WARNING: cooldown is active until {cooldown.astimezone():%Y-%m-%d %H:%M}. "
                      "Etsy just showed a warning; continuing now adds risk to your account.")
                if not assume_yes and input_fn("Type YES to run anyway: ").strip() != "YES":
                    print("Cancelled.")
                    return 1
            log = _make_logger(base, now_fn(), log_file)
            rng = random.Random()
            pacer = Pacer(cfg, rng)
            with interrupt_on_signals(), _open_insights(cfg, pacer, rng, log) as page:
                deps = SessionDeps(store=store, page=page, parse=parse_search, pacer=pacer, cfg=cfg,
                                   clock=now_fn, sleep=time.sleep, log=log, parser_version=PARSER_VERSION)
                summary = run_session(deps, max_keywords=UJI_SEARCHES if uji else None,
                                      ignore_cooldown=ignore_cooldown)
            print()
            print(format_summary(summary))
            return 0
    finally:
        store.close()


def main(argv: list[str] | None = None, *, base_dir: Path | None = None,
         now: Callable[[], datetime] | None = None, input_fn: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(prog="etsy_insights", description="Etsy keyword opportunity finder")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the daily session (slow searches in the 'Etsy Riset' Chrome)")
    run.add_argument("--uji", action="store_true", help=f"Test run: only {UJI_SEARCHES} searches")
    run.add_argument("--abaikan-pendinginan", action="store_true",
                     help="Run even during cooldown (asks you to type YES)")
    run.add_argument("--yes", action="store_true", help="Answer YES to the cooldown question (used by the app)")
    run.add_argument("--log-file", type=Path, help="Write the session log to this file")
    sub.add_parser("status", help="Show the queue, today's searches and the last session")
    sub.add_parser("export", help="Create the latest Excel file")
    sub.add_parser("kenali", help="Recording mode: record Marketplace Insights data while you search by hand")
    args = parser.parse_args(argv)

    base = Path(base_dir) if base_dir else app_home()
    now_fn = now or (lambda: datetime.now().astimezone())
    try:
        cfg, warnings = load_config(base / "config.toml")
        for warning in warnings:
            print(f"Config warning: {warning}")
        if args.command == "run":
            return _run(base, cfg, now_fn, args.uji, args.abaikan_pendinginan, input_fn,
                        assume_yes=args.yes, log_file=args.log_file)
        if args.command == "status":
            return _status(base, cfg, now_fn())
        if args.command == "export":
            return _export(base, cfg, now_fn())
        return _kenali(base, cfg, now_fn)
    except (ConfigError, ChromeNotFound, PortBusy, ChromeStartTimeout) as exc:
        print(str(exc))
        return 1
    except PlaywrightError as exc:
        print(f"Chrome closed or not responding: {exc}\nRun the command again to retry.")
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except Exception as exc:  # pesan yang bisa dibaca, bukan traceback
        print(f"Unexpected error: {type(exc).__name__}: {exc}\n"
              "Copy this message and send it to Claude.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
