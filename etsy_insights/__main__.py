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
from .parser import PARSER_VERSION, parse_search
from .planner import upcoming
from .recorder import run_kenali
from .score import score_all
from .session import REASON_TEXT, SessionDeps, StopReason, format_summary, run_session
from .store import Store, read_keywords_file
from .taste import build_profiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UJI_SEARCHES = 3


def _open_store(base: Path, now: datetime) -> Store:
    store = Store(base / "data" / "etsy.db")
    store.sync_user_keywords(read_keywords_file(base / "keywords.txt"), now)
    return store


def _reason_text(code: str | None) -> str:
    if code is None:
        return "belum selesai"
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
        yield EtsyInsightsPage(context, pacer, rng, log=log)


def _status(base: Path, cfg: Config, now: datetime) -> int:
    store = _open_store(base, now)
    counts = store.status_counts()
    checked = store.checked_on(now.date(), now.tzinfo)
    print(f"Antrean: {counts.get('pending', 0)} menunggu, {counts.get('harvested', 0)} hasil panen, "
          f"{counts.get('done', 0)} sudah dicari, {counts.get('no_data', 0)} tanpa data, "
          f"{counts.get('failed', 0)} gagal")
    print(f"Hari ini: {checked}/{cfg.kuota_harian} keyword dicek (sisa {remaining_quota(cfg, checked)})")
    cooldown = store.active_cooldown_until(now)
    if cooldown is not None:
        print(f"Masa pendinginan sampai: {cooldown.astimezone():%Y-%m-%d %H:%M}")
    last = store.last_session()
    if last is not None:
        print(f"Sesi terakhir: {last['started_at'].astimezone():%Y-%m-%d %H:%M}, "
              f"{last['checked_count']} keyword. {_reason_text(last['stop_reason'])}")
    store.close()
    return 0


def _export(base: Path, cfg: Config, now: datetime) -> int:
    store = _open_store(base, now)
    path = export_excel(score_all(store.latest_results(), cfg), store.all_results(), upcoming(store, cfg),
                        base / "hasil", now.date(), profiles=build_profiles(store))
    store.close()
    print(f"File Excel: {path}")
    return 0


def _kenali(base: Path, cfg: Config, now_fn: Callable[[], datetime]) -> int:
    endpoint = ensure_chrome(cfg.port_debug)
    with connected_browser(endpoint) as context:
        run_kenali(context, base / "rekaman", now_fn)
    return 0


def _make_logger(base: Path, now: datetime) -> Callable[[str], None]:
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"sesi-{now:%Y%m%d-%H%M%S}.log"

    def log(message: str) -> None:
        print(message)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%H:%M:%S} {message}\n")
    return log


def _run(base: Path, cfg: Config, now_fn: Callable[[], datetime], uji: bool, ignore_cooldown: bool,
         input_fn: Callable[[str], str]) -> int:
    store = _open_store(base, now_fn())
    try:
        with session_lock(base / "data" / "sesi.lock") as locked:
            if not locked:
                print("Sesi lain sedang berjalan. Tunggu sampai selesai.")
                return 1
            cooldown = store.active_cooldown_until(now_fn())
            if ignore_cooldown and cooldown is not None:
                print(f"PERINGATAN: masa pendinginan masih berlaku sampai {cooldown.astimezone():%Y-%m-%d %H:%M}. "
                      "Etsy baru saja menampilkan tanda bahaya; melanjutkan sekarang menambah risiko akun.")
                if input_fn("Ketik YA untuk tetap menjalankan: ").strip() != "YA":
                    print("Dibatalkan.")
                    return 1
            log = _make_logger(base, now_fn())
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
    parser = argparse.ArgumentParser(prog="etsy_insights", description="Pencari peluang keyword Etsy")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Jalankan sesi harian (pencarian pelan di Chrome 'Etsy Riset')")
    run.add_argument("--uji", action="store_true", help=f"Hanya {UJI_SEARCHES} pencarian untuk uji coba")
    run.add_argument("--abaikan-pendinginan", action="store_true",
                     help="Jalankan meski masa pendinginan masih berlaku (minta konfirmasi YA)")
    sub.add_parser("status", help="Tampilkan antrean, kuota hari ini, dan sesi terakhir")
    sub.add_parser("export", help="Buat file Excel hasil terbaru")
    sub.add_parser("kenali", help="Rekam data halaman Marketplace Insights saat Anda mencari manual")
    args = parser.parse_args(argv)

    base = Path(base_dir) if base_dir else PROJECT_ROOT
    now_fn = now or (lambda: datetime.now().astimezone())
    try:
        cfg, warnings = load_config(base / "config.toml")
        for warning in warnings:
            print(f"Peringatan config: {warning}")
        if args.command == "run":
            return _run(base, cfg, now_fn, args.uji, args.abaikan_pendinginan, input_fn)
        if args.command == "status":
            return _status(base, cfg, now_fn())
        if args.command == "export":
            return _export(base, cfg, now_fn())
        return _kenali(base, cfg, now_fn)
    except (ConfigError, ChromeNotFound, PortBusy, ChromeStartTimeout) as exc:
        print(str(exc))
        return 1
    except PlaywrightError as exc:
        print(f"Chrome tertutup atau tidak merespons: {exc}\nJalankan lagi perintahnya untuk mencoba ulang.")
        return 1
    except KeyboardInterrupt:
        print("\nDihentikan.")
        return 130
    except Exception as exc:  # pesan yang bisa dibaca, bukan traceback
        print(f"Terjadi kesalahan tak terduga: {type(exc).__name__}: {exc}\n"
              "Salin pesan ini dan kirim ke Claude.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
