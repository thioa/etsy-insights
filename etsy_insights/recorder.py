"""Mode kenal-halaman: merekam data yang dimuat Marketplace Insights saat Anda mencari manual.

Tidak ada otomatisasi di sini. Pengguna sendiri yang mengetik keyword di Chrome. Nilai sensitif
(token, email, cookie, dll.) disensor sebelum disimpan, dan header request/cookie tidak direkam.
"""
from __future__ import annotations

import base64
import json
import re
import select
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SENSITIVE_KEYS = ("csrf", "token", "email", "session", "cookie", "password", "secret",
                  "auth", "phone", "address", "nonce", "nnc")
REDACTED = "[DIHAPUS]"
MAX_BODY_CHARS = 2_000_000
FORMAT = "etsy-insights-kenali/1"
INSIGHTS_URL = "https://www.etsy.com/your/shops/me/marketplace-insights"
_TRUNCATED = "...[TERPOTONG]"

_SENS = "|".join(re.escape(k) for k in SENSITIVE_KEYS)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_JSON_PAIR_RE = re.compile(rf'("[^"\\]*(?:{_SENS})[^"\\]*"\s*:\s*)("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?)', re.I)
_ESCAPED_PAIR_RE = re.compile(rf'(\\"[^"\\]*(?:{_SENS})[^"\\]*\\"\s*:\s*)\\"(?:[^"\\]|\\[^"])*\\"', re.I)
_SENSITIVE_TAG_RE = re.compile(rf'<[^>]*\b(?:name|id|property)\s*=\s*"[^"]*(?:{_SENS})[^"]*"[^>]*>', re.I)
_TAG_VALUE_RE = re.compile(r'\b(value|content)\s*=\s*"[^"]*"', re.I)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(k in lowered for k in SENSITIVE_KEYS)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if _is_sensitive(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def redact_html(text: str) -> str:
    text = _SENSITIVE_TAG_RE.sub(lambda m: _TAG_VALUE_RE.sub(rf'\1="{REDACTED}"', m.group(0)), text)
    text = _JSON_PAIR_RE.sub(rf'\1"{REDACTED}"', text)
    text = _ESCAPED_PAIR_RE.sub(rf'\1\\"{REDACTED}\\"', text)
    return _EMAIL_RE.sub(REDACTED, text)


def _redact_url(url: str) -> str:
    parts = urlparse(url)
    if not parts.query:
        return url
    query = [(k, REDACTED if _is_sensitive(k) else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunparse(parts._replace(query=urlencode(query)))


def _is_etsy(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "etsy.com" or host.endswith(".etsy.com")


@dataclass
class Recording:
    started_at: datetime
    responses: list[dict] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)

    def add_response(self, url: str, status: int, content_type: str, body_text: str, at: datetime) -> bool:
        if not _is_etsy(url) or "json" not in content_type.lower():
            return False
        if len(body_text) > MAX_BODY_CHARS:
            body: Any = redact_html(body_text[:MAX_BODY_CHARS]) + _TRUNCATED
        else:
            try:
                body = redact(json.loads(body_text))
            except ValueError:
                body = redact_html(body_text)
        self.responses.append({"t": at.isoformat(), "url": _redact_url(url), "status": status,
                               "content_type": content_type, "body": body})
        return True

    def add_snapshot(self, page_url: str, html: str, png: bytes, at: datetime) -> None:
        self.snapshots.append({"t": at.isoformat(), "page_url": _redact_url(page_url), "html": redact_html(html),
                               "screenshot_png_base64": base64.b64encode(png).decode("ascii")})

    def to_dict(self) -> dict:
        return {"format": FORMAT, "started_at": self.started_at.isoformat(),
                "responses": self.responses, "snapshots": self.snapshots}

    def save(self, out_dir: Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"kenali-{self.started_at:%Y%m%d-%H%M}.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        return path


def wait_for_line(context, stdin) -> str:
    """Tunggu satu baris dari terminal sambil tetap memproses event Chrome."""
    while True:
        pages = context.pages
        if pages:
            pages[0].wait_for_timeout(250)
        else:
            time.sleep(0.25)
        ready, _, _ = select.select([stdin], [], [], 0)
        if ready:
            line = stdin.readline()
            if line == "":  # stdin ditutup
                return "selesai"
            return line.strip()


def run_kenali(context, out_dir: Path, clock: Callable[[], datetime], stdin=sys.stdin, print_fn=print) -> Path:
    recording = Recording(clock())

    def on_response(response) -> None:
        try:
            content_type = response.headers.get("content-type", "")
            if not _is_etsy(response.url) or "json" not in content_type.lower():
                return
            recording.add_response(response.url, response.status, content_type, response.text(), clock())
        except Exception:  # respons yang sudah hilang/terputus diabaikan saja
            pass

    context.on("response", on_response)
    page = context.new_page()
    print_fn("Membuka Marketplace Insights di Chrome 'Etsy Riset'...")
    page.goto(INSIGHTS_URL, wait_until="domcontentloaded")
    while "signin" in page.url:
        print_fn("Anda belum login. Silakan login ke Etsy di jendela Chrome itu, "
                 "lalu tekan Enter di sini (atau ketik 'selesai' untuk batal).")
        if wait_for_line(context, stdin).lower() == "selesai":
            break
        if "marketplace-insights" not in page.url:
            page.goto(INSIGHTS_URL, wait_until="domcontentloaded")

    print_fn("\nLangkah:\n"
             "  1. Di Chrome, ketik satu keyword di kotak pencarian Marketplace Insights,\n"
             "     lalu tunggu sampai hasilnya muncul.\n"
             "  2. Kembali ke jendela Terminal ini dan tekan Enter untuk merekam.\n"
             "  3. Ulangi untuk 2-3 keyword. Setelah itu ketik 'selesai' lalu Enter.\n")
    while True:
        line = wait_for_line(context, stdin)
        if line.lower() == "selesai":
            break
        for tab in context.pages:
            if "etsy.com" in tab.url:
                recording.add_snapshot(tab.url, tab.content(), tab.screenshot(full_page=True), clock())
        print_fn(f"Terekam: {len(recording.snapshots)} snapshot, {len(recording.responses)} respons data. "
                 "Cari keyword berikutnya, atau ketik 'selesai'.")

    path = recording.save(out_dir)
    print_fn(f"\nRekaman disimpan di:\n  {path}\n"
             "Kirim file ini ke Claude (beserta screenshot halaman Insights Anda).\n"
             "Chrome 'Etsy Riset' boleh dibiarkan terbuka.")
    return path
