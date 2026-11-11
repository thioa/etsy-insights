"""Klien API Printify yang hanya membaca (GET), dengan jeda antar permintaan dan coba ulang (spec Tahap 4 §5)."""
from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

BASE_URL = "https://api.printify.com"
USER_AGENT = "EtsyInsights/4.0"
PAGE_SIZE = 50
RETRY_AFTER_DEFAULT = 60
MAX_RATE_RETRIES = 3
SERVER_BACKOFF = (5, 15, 45)
SCOPES = "shops.read, products.read and catalog.read"


class PrintifyError(Exception):
    message = "Printify could not be read."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class TokenRejected(PrintifyError):
    message = "Printify rejected the token. Create a new token in Printify and paste it here."


class MissingScope(PrintifyError):
    def __init__(self, scope: str) -> None:
        self.scope = scope
        super().__init__(f"The token needs the {scope} permission. Create a new token with {SCOPES}.")


class PrintifyBusy(PrintifyError):
    message = "Printify is busy. Try Sync again in a few minutes."


class PrintifyUnreachable(PrintifyError):
    message = "Could not reach Printify. Check your internet connection and try again."


class UnexpectedResponse(PrintifyError):
    message = "Printify sent data in an unexpected format."

    def __init__(self, path: str, body: str) -> None:
        self.path = path
        self.body = body
        super().__init__()


def scope_for(path: str) -> str:
    if path.startswith("/v1/catalog/"):
        return "catalog.read"
    if path == "/v1/shops.json":
        return "shops.read"
    return "products.read"


def _retry_after(value: str | None) -> float:
    try:
        seconds = float(value) if value is not None else RETRY_AFTER_DEFAULT
    except ValueError:
        return RETRY_AFTER_DEFAULT
    return seconds if seconds >= 0 else RETRY_AFTER_DEFAULT


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Jangan pernah ikuti redirect: header Authorization tidak boleh sampai ke host lain."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PrintifyClient:
    def __init__(self, token: str, *, base_url: str = BASE_URL, min_interval: float = 1.0, timeout: float = 30,
                 clock=time.monotonic, sleep=time.sleep, no_proxy: bool = False) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._min_interval = min_interval
        self._timeout = timeout
        self._clock = clock
        self._sleep = sleep
        handlers = [_NoRedirect] + ([urllib.request.ProxyHandler({})] if no_proxy else [])
        self._opener = urllib.request.build_opener(*handlers)
        self._last: float | None = None

    def _pace(self) -> None:
        if self._last is not None:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)

    def _once(self, url: str) -> tuple[int, str, dict]:
        self._pace()
        request = urllib.request.Request(url, method="GET", headers={
            "Authorization": f"Bearer {self._token}", "User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return response.status, response.read().decode("utf-8", errors="replace"), dict(response.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return exc.code, body, dict(exc.headers or {})
        finally:
            self._last = self._clock()

    def get(self, path: str, params: dict | None = None) -> Any:
        url = self._base + path + (f"?{urlencode(params)}" if params else "")
        rate_retries = server_retries = 0
        while True:
            try:
                status, body, headers = self._once(url)
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError,
                    http.client.HTTPException):
                status, body, headers = None, "", {}
            if status == 429:
                if rate_retries >= MAX_RATE_RETRIES:
                    raise PrintifyBusy()
                rate_retries += 1
                self._sleep(_retry_after(headers.get("Retry-After")))
                continue
            if status is None or status >= 500:
                if server_retries >= len(SERVER_BACKOFF):
                    raise PrintifyUnreachable()
                self._sleep(SERVER_BACKOFF[server_retries])
                server_retries += 1
                continue
            if status == 401:
                raise TokenRejected()
            if status == 403:
                raise MissingScope(scope_for(path))
            if status != 200:
                raise UnexpectedResponse(path, body[:2000])
            try:
                return json.loads(body)
            except ValueError:
                raise UnexpectedResponse(path, body[:2000]) from None

    def _list(self, path: str) -> list:
        value = self.get(path)
        if not isinstance(value, list):
            raise UnexpectedResponse(path, json.dumps(value)[:2000])
        return value

    def shops(self) -> list[dict]:
        return self._list("/v1/shops.json")

    def products(self, shop_id: int) -> list[dict]:
        path = f"/v1/shops/{shop_id}/products.json"
        items: list[dict] = []
        page = 1
        while True:
            value = self.get(path, {"page": page, "limit": PAGE_SIZE})
            if not isinstance(value, dict) or not isinstance(value.get("data"), list):
                raise UnexpectedResponse(path, json.dumps(value)[:2000])
            items.extend(value["data"])
            last = value.get("last_page")
            if not value["data"] or not isinstance(last, int) or page >= last:
                return items
            page += 1

    def blueprints(self) -> list[dict]:
        return self._list("/v1/catalog/blueprints.json")

    def providers(self, blueprint_id: int) -> list[dict]:
        return self._list(f"/v1/catalog/blueprints/{blueprint_id}/print_providers.json")

    def shipping(self, blueprint_id: int, provider_id: int) -> dict:
        path = f"/v1/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/shipping.json"
        value = self.get(path)
        if not isinstance(value, dict):
            raise UnexpectedResponse(path, json.dumps(value)[:2000])
        return value
