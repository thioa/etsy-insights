"""Server Printify palsu (HTTP lokal, di thread) untuk tes. Tidak pernah menghubungi Printify."""
from __future__ import annotations

import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from tests import printify_data as data

SLOW = "__slow__"
TRUNCATE = "__truncate__"


class FakePrintify:
    def __init__(self, tls: tuple | None = None) -> None:
        self.routes: dict[str, tuple[int, object, dict]] = {}
        self.queues: dict[str, list[tuple[int, object, dict]]] = {}
        self.requests: list[tuple[str, str, dict, dict]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # tenang di output tes
                pass

            def _answer(self):
                parts = urlsplit(self.path)
                query = {k: v[0] for k, v in parse_qs(parts.query).items()}
                fake.requests.append((self.command, parts.path, query, dict(self.headers)))
                key = parts.path + ("?page=" + query["page"] if "page" in query else "")
                queue = fake.queues.get(key) or fake.queues.get(parts.path)
                if queue:
                    status, body, headers = queue.pop(0)
                else:
                    status, body, headers = fake.routes.get(key) or fake.routes.get(
                        parts.path, (404, {"error": "not found"}, {}))
                if body == SLOW:  # jawab setelah batas waktu klien habis
                    time.sleep(0.6)
                    body = data.SHOPS
                if body == TRUNCATE:  # koneksi putus di tengah jawaban
                    self.send_response(status)
                    self.send_header("Content-Length", "1000")
                    self.end_headers()
                    self.wfile.write(b'[{"id": 1')
                    self.close_connection = True
                    return
                payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _answer
            do_POST = _answer

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._scheme = "http"
        if tls:  # HTTPS dengan sertifikat sendiri (cert, key)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(tls[0]), str(tls[1]))
            self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
            self._scheme = "https"
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    @property
    def url(self) -> str:
        return f"{self._scheme}://127.0.0.1:{self._server.server_address[1]}"

    def set(self, path: str, body, status: int = 200, headers: dict | None = None) -> None:
        self.routes[path] = (status, body, headers or {})

    def queue(self, path: str, *responses) -> None:
        self.queues[path] = [(s, b, h or {}) for s, b, h in responses]

    def load_default(self) -> FakePrintify:
        self.set("/v1/shops.json", data.SHOPS)
        self.set("/v1/shops/111/products.json?page=1", data.PRODUCTS_PAGE_1)
        self.set("/v1/shops/111/products.json?page=2", data.PRODUCTS_PAGE_2)
        self.set("/v1/catalog/blueprints.json", data.BLUEPRINTS)
        for blueprint_id, providers in data.PROVIDERS.items():
            self.set(f"/v1/catalog/blueprints/{blueprint_id}/print_providers.json", providers)
        for (blueprint_id, provider_id), shipping in data.SHIPPING.items():
            self.set(f"/v1/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/shipping.json", shipping)
        return self

    def __enter__(self) -> FakePrintify:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
