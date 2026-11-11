"""Membuka Chrome asli dengan profil "Etsy Riset" dan menyambung lewat DevTools Protocol.

Chrome diluncurkan sebagai proses biasa (bukan oleh Playwright), jadi tidak ada flag
--enable-automation, tidak ada banner "controlled by automated software", dan
navigator.webdriver tetap false.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PROFILE_DIR = Path.home() / "Library/Application Support/EtsyRiset/chrome-profile"
_POLL_SECONDS = 0.5


class ChromeNotFound(Exception):
    pass


class PortBusy(Exception):
    pass


class ChromeStartTimeout(Exception):
    pass


def chrome_args(chrome_path: Path, port: int, profile_dir: Path, extra_args: Sequence[str] = ()) -> list[str]:
    return [str(chrome_path), f"--user-data-dir={profile_dir}", f"--remote-debugging-port={port}",
            "--no-first-run", "--no-default-browser-check", *extra_args]


def probe_debug_port(port: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ensure_chrome(port: int, profile_dir: Path = PROFILE_DIR, chrome_path: Path = CHROME_PATH,
                  extra_args: Sequence[str] = (), *, launch=subprocess.Popen, probe=probe_debug_port,
                  in_use=port_in_use, sleep=time.sleep, wait_seconds: float = 15.0) -> str:
    """Pastikan Chrome profil Etsy Riset berjalan dengan port debug; kembalikan endpoint-nya."""
    endpoint = f"http://127.0.0.1:{port}"
    info = probe(port)
    if info and "Chrome" in str(info.get("Browser", "")):
        return endpoint
    if in_use(port):
        raise PortBusy(f"Port {port} sedang dipakai program lain. Ubah port_debug di config.toml "
                       "(misalnya 9223), lalu coba lagi.")
    if not Path(chrome_path).exists():
        raise ChromeNotFound(f"Google Chrome tidak ditemukan di {chrome_path}. "
                             "Pasang Chrome dari https://www.google.com/chrome/ lalu coba lagi.")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    launch(chrome_args(chrome_path, port, profile_dir, extra_args),
           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(max(1, int(wait_seconds / _POLL_SECONDS))):
        info = probe(port)
        if info and "Chrome" in str(info.get("Browser", "")):
            return endpoint
        sleep(_POLL_SECONDS)
    raise ChromeStartTimeout(f"Chrome tidak merespons dalam {wait_seconds:.0f} detik. Tutup semua jendela "
                             "Chrome 'Etsy Riset' (atau restart Mac), lalu coba lagi.")


@contextmanager
def connected_browser(endpoint: str) -> Iterator["BrowserContext"]:  # noqa: F821
    """Sambung ke Chrome yang sudah berjalan. Saat selesai, Chrome tetap dibiarkan terbuka."""
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(endpoint)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        yield context
    finally:
        playwright.stop()
