"""Perintah: python -m etsy_insights {status|export|kenali}"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from .browser import ChromeNotFound, ChromeStartTimeout, PortBusy, connected_browser, ensure_chrome
from .config import Config, ConfigError, load_config
from .export import export_excel
from .pacer import remaining_quota
from .recorder import run_kenali
from .score import score_all
from .store import Store, read_keywords_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _open_store(base: Path, now: datetime) -> Store:
    store = Store(base / "data" / "etsy.db")
    store.sync_user_keywords(read_keywords_file(base / "keywords.txt"), now)
    return store


def _status(base: Path, cfg: Config, now: datetime) -> int:
    store = _open_store(base, now)
    counts = store.status_counts()
    checked = store.checked_on(now.date(), now.tzinfo)
    print(f"Antrean: {counts.get('pending', 0)} menunggu, {counts.get('done', 0)} selesai, "
          f"{counts.get('no_data', 0)} tanpa data, {counts.get('failed', 0)} gagal")
    print(f"Hari ini: {checked}/{cfg.kuota_harian} keyword dicek "
          f"(sisa {remaining_quota(cfg, checked)})")
    cooldown = store.active_cooldown_until(now)
    if cooldown is not None:
        print(f"Masa pendinginan sampai: {cooldown.astimezone():%Y-%m-%d %H:%M}")
    last = store.last_session()
    if last is not None:
        print(f"Sesi terakhir: {last['started_at'].astimezone():%Y-%m-%d %H:%M}, "
              f"{last['checked_count']} keyword, alasan berhenti: {last['stop_reason'] or 'belum selesai'}")
    store.close()
    return 0


def _export(base: Path, cfg: Config, now: datetime) -> int:
    store = _open_store(base, now)
    path = export_excel(score_all(store.latest_results(), cfg), store.all_results(), store.pending_queue(),
                        base / "hasil", now.date())
    store.close()
    print(f"File Excel: {path}")
    return 0


def _kenali(base: Path, cfg: Config, now_fn: Callable[[], datetime]) -> int:
    endpoint = ensure_chrome(cfg.port_debug)
    with connected_browser(endpoint) as context:
        run_kenali(context, base / "rekaman", now_fn)
    return 0


def main(argv: list[str] | None = None, *, base_dir: Path | None = None,
         now: Callable[[], datetime] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etsy_insights", description="Pencari peluang keyword Etsy")
    sub = parser.add_subparsers(dest="command", required=True)
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
        if args.command == "status":
            return _status(base, cfg, now_fn())
        if args.command == "export":
            return _export(base, cfg, now_fn())
        return _kenali(base, cfg, now_fn)
    except (ConfigError, ChromeNotFound, PortBusy, ChromeStartTimeout) as exc:
        print(str(exc))
        return 1
    except PlaywrightError as exc:
        print(f"Chrome tertutup atau tidak merespons: {exc}\nBuka lagi kenali.command untuk mencoba ulang.")
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
