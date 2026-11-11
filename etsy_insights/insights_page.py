"""Mengendalikan halaman Marketplace Insights di Chrome "Etsy Riset" seperti orang biasa.

Data hanya dibaca dari respons yang dimuat halaman itu sendiri; tidak ada request tambahan ke Etsy.
"""
from __future__ import annotations

import random
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .models import BrowserClosed, CapturedResponse, DangerSignal, NotLoggedIn, PageLoadTimeout, RawResult
from .pacer import Pacer
from .parser import blocked_quota, is_results_for, related_rows_for

DASHBOARD_URL = "https://www.etsy.com/your/shops/me/dashboard"
INSIGHTS_URL = "https://www.etsy.com/your/shops/me/marketplace-insights"
NAV_SELECTOR = 'a[data-app-key="marketplace-insights"]'
SEARCH_INPUT_SELECTORS = ('input[aria-label="Input to search for keywords"]', 'input[placeholder*="keyword" i]',
                          'main input[type="search"]', 'main input[type="text"]')
CAPTCHA_MARKERS = ("captcha", "datadome", "challenges.cloudflare.com", "hcaptcha", "recaptcha")
VERIFY_TEXTS = ("verify you are a human", "verify you're a human", "unusual activity", "are you a robot",
                "press & hold")
_DANGER_RESOURCE_TYPES = ("document", "xhr", "fetch")
_POLL_MS = 250
_CHECK_ATTEMPTS = 3


def _without_query(url: str) -> str:
    """Host + path saja: query berisi keyword (mis. "book signing") dan tidak boleh memicu tanda bahaya."""
    parts = urlparse(url)
    return f"{parts.netloc}{parts.path}".lower()


def is_login_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return "/signin" in path or "/login" in path


def detect_danger(url: str, frame_urls: Sequence[str], body_text: str,
                  http_statuses: Sequence[int]) -> DangerSignal | None:
    if is_login_url(url):
        return DangerSignal("login", url)
    for candidate in (url, *frame_urls):
        if any(marker in _without_query(candidate) for marker in CAPTCHA_MARKERS):
            return DangerSignal("captcha", candidate)
    text = body_text.lower()
    for phrase in VERIFY_TEXTS:
        if phrase in text:
            return DangerSignal("verifikasi", phrase)
    if 429 in http_statuses:
        return DangerSignal("http_429", "Etsy membalas 429 (terlalu banyak permintaan)")
    if 403 in http_statuses:
        return DangerSignal("http_403", "Etsy membalas 403 (akses ditolak)")
    return None


def has_results_for(captured: Sequence[CapturedResponse], keyword: str) -> bool:
    return any(is_results_for(r, keyword) for r in captured)


def has_related_for(captured: Sequence[CapturedResponse], keyword: str) -> bool:
    return related_rows_for(captured, keyword) is not None


def _is_etsy(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "etsy.com" or host.endswith(".etsy.com")


@contextmanager
def _translate_errors() -> Iterator[None]:
    """Ubah error Playwright menjadi error milik aplikasi."""
    try:
        yield
    except PlaywrightTimeout as exc:
        raise PageLoadTimeout(str(exc).splitlines()[0]) from exc
    except PlaywrightError as exc:
        if "closed" in str(exc).lower():
            raise BrowserClosed(str(exc).splitlines()[0]) from exc
        raise PageLoadTimeout(str(exc).splitlines()[0]) from exc


class EtsyInsightsPage:
    def __init__(self, context, pacer: Pacer, rng: random.Random, *, dashboard_url: str = DASHBOARD_URL,
                 settle_seconds: tuple[float, float] = (3, 8), input_timeout: float = 10,
                 results_timeout: float = 30, related_timeout: float = 20,
                 log: Callable[[str], None] = lambda message: None) -> None:
        self._context = context
        self._pacer = pacer
        self._rng = rng
        self._dashboard_url = dashboard_url
        self._settle = settle_seconds
        self._input_timeout = input_timeout
        self._results_timeout = results_timeout
        self._related_timeout = related_timeout
        self._log = log
        self._page = None
        self._captured: list[CapturedResponse] = []
        self._http_statuses: list[int] = []
        context.on("response", self._on_response)

    # --- pencatatan respons -------------------------------------------------
    def _on_response(self, response) -> None:
        try:
            url = response.url
            if not _is_etsy(url):
                return
            status = response.status
            if status in (403, 429) and response.request.resource_type in _DANGER_RESOURCE_TYPES:
                self._http_statuses.append(status)
            if "/marketplace-insights/" not in urlparse(url).path:
                return
            if "json" not in response.headers.get("content-type", "").lower():
                return
            try:
                body = response.json()
            except Exception:  # body kosong / bukan JSON
                body = None
            self._captured.append(CapturedResponse(url, status, body))
        except Exception:  # respons yang sudah hilang diabaikan
            pass

    def close(self) -> None:
        """Lepas pendengar respons dari context (Chrome tetap terbuka)."""
        try:
            self._context.remove_listener("response", self._on_response)
        except Exception:
            pass

    # --- InsightsPage ----------------------------------------------------------
    def _blocked_now(self) -> bool:
        """Tanda bahaya yang sudah terlihat tanpa membaca isi halaman (status HTTP / URL)."""
        page = self._page
        frame_urls = [frame.url for frame in page.frames]
        return bool(self._http_statuses) or detect_danger(page.url, frame_urls, "", ()) is not None

    def open(self) -> None:
        self._http_statuses.clear()
        with _translate_errors():
            page = self._page = self._context.new_page()
            page.goto(self._dashboard_url, wait_until="domcontentloaded")
            if is_login_url(page.url):
                raise NotLoggedIn("The 'Etsy Riset' Chrome is not signed in to Etsy.")
            if self._blocked_now():
                self._log("Etsy showed a warning on the dashboard; not continuing.")
                return
            page.wait_for_timeout(self._rng.uniform(*self._settle) * 1000)
            nav = page.locator(NAV_SELECTOR).first
            try:
                nav.wait_for(state="visible", timeout=10_000)
            except PlaywrightTimeout:
                self._log("Marketplace Insights menu not found, opening it directly.")
                page.goto(INSIGHTS_URL, wait_until="domcontentloaded")
            else:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                    nav.click()
            if is_login_url(page.url):
                raise NotLoggedIn("The 'Etsy Riset' Chrome is not signed in to Etsy.")

    def _find_search_box(self):
        page = self._page
        deadline = time.monotonic() + self._input_timeout
        while True:
            for selector in SEARCH_INPUT_SELECTORS:
                box = page.locator(selector).first
                if box.count() and box.is_visible():
                    return box
            if time.monotonic() > deadline:
                raise PageLoadTimeout("Search box not found (Etsy's page may have changed).")
            page.wait_for_timeout(200)

    def search(self, keyword: str) -> RawResult:
        page = self._page
        mark = len(self._captured)
        with _translate_errors():
            page.wait_for_timeout(_POLL_MS)  # proses respons yang datang selama jeda (mis. 429 terlambat)
            if self._blocked_now():
                return RawResult(keyword, page.url, (), "")  # jangan mengetik apa pun; sesi akan berhenti
            box = self._find_search_box()
            size = box.bounding_box() or {"width": 200, "height": 30}
            box.click(position={"x": size["width"] * self._rng.uniform(0.2, 0.8),
                                "y": size["height"] * self._rng.uniform(0.3, 0.7)})
            page.keyboard.press("Meta+A" if sys.platform == "darwin" else "Control+A")
            page.keyboard.press("Backspace")
            for char in keyword:
                page.keyboard.type(char)
                page.wait_for_timeout(self._pacer.typing_delay_ms())
            page.keyboard.press("Enter")

            deadline = time.monotonic() + self._results_timeout
            while not has_results_for(self._captured[mark:], keyword):
                if self._http_statuses or is_login_url(page.url) or blocked_quota(self._captured[mark:], keyword):
                    break  # tanda bahaya / kuota Etsy: biarkan sesi memeriksa dan berhenti
                if time.monotonic() > deadline:
                    raise PageLoadTimeout(f"No data for '{keyword}' within {self._results_timeout:.0f} seconds.")
                page.wait_for_timeout(_POLL_MS)
            else:
                deadline = time.monotonic() + self._related_timeout
                while not has_related_for(self._captured[mark:], keyword) and time.monotonic() < deadline:
                    page.wait_for_timeout(_POLL_MS)
            return RawResult(keyword, page.url, tuple(self._captured[mark:]), "")

    def check_danger(self) -> DangerSignal | None:
        page = self._page
        if page is None:
            return None
        snapshot = {"text": "", "iframes": []}
        for attempt in range(_CHECK_ATTEMPTS):
            try:
                snapshot = page.evaluate(
                    "() => ({text: document.body ? document.body.innerText.slice(0, 20000) : '',"
                    " iframes: Array.from(document.querySelectorAll('iframe')).map(f => f.src || '')})")
                break
            except PlaywrightError as exc:
                if "closed" in str(exc).lower():
                    raise BrowserClosed(str(exc).splitlines()[0]) from exc
                # Halaman sedang berpindah (mis. dialihkan ke login/captcha): tunggu lalu coba lagi.
                if attempt < _CHECK_ATTEMPTS - 1:
                    with _translate_errors():
                        page.wait_for_timeout(1000)
        with _translate_errors():
            frame_urls = [frame.url for frame in page.frames] + list(snapshot["iframes"])
            return detect_danger(page.url, frame_urls, snapshot["text"], self._http_statuses)

    def dwell(self, seconds: float, scroll: bool) -> None:
        page = self._page
        scroll_times = sorted(self._rng.uniform(0, seconds) for _ in range(self._rng.randint(2, 3))) if scroll else []
        elapsed = 0.0
        with _translate_errors():
            while elapsed < seconds:
                step = min(1.0, seconds - elapsed)
                page.wait_for_timeout(step * 1000)
                elapsed += step
                while scroll_times and scroll_times[0] <= elapsed:
                    scroll_times.pop(0)
                    page.mouse.wheel(0, self._rng.randint(200, 600))
