"""Server Anthropic palsu (HTTP lokal, di thread) untuk tes. Tidak pernah menghubungi Anthropic.

Menjawab dengan bentuk Messages API: JSON biasa, atau streaming SSE (`event: <type>` + `data: <json>`).
"""
from __future__ import annotations

import json
import ssl
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

MODEL = "claude-opus-5-5"


@dataclass
class Sse:
    events: list[dict]


@dataclass
class Json:
    status: int
    body: dict = field(default_factory=dict)


@dataclass
class Truncated:
    """Streaming yang putus di tengah: Content-Length lebih besar dari yang dikirim, lalu koneksi ditutup."""
    events: list[dict]


DROP = object()  # koneksi ditutup tanpa jawaban


def error_body(kind: str, message: str) -> dict:
    return {"type": "error", "error": {"type": kind, "message": message}}


def error_event(kind: str, message: str) -> dict:
    return error_body(kind, message)


def model_body(model: str = MODEL) -> dict:
    return {"type": "model", "id": model, "display_name": "Claude Opus 5.5", "created_at": "2026-01-01T00:00:00Z"}


def text_block(text: str, citations=()) -> dict:
    return {"type": "text", "text": text, "citations": [
        {"type": "web_search_result_location", "url": url, "title": title, "encrypted_index": "e", "cited_text": "c"}
        for url, title in citations]}


_ids = iter(range(1, 1_000_000))


def fallback_block(from_model: str = MODEL, to_model: str = "claude-opus-4-8") -> dict:
    """Batas saat model pertama menolak dan model fallback melanjutkan jawaban."""
    return {"type": "fallback", "from": {"model": from_model}, "to": {"model": to_model},
            "trigger": {"type": "refusal", "category": None}}


def search_blocks(query: str, results) -> list[dict]:
    tool_id = f"srvtoolu_{next(_ids)}"
    return [{"type": "server_tool_use", "id": tool_id, "name": "web_search", "input": {"query": query}},
            {"type": "web_search_tool_result", "tool_use_id": tool_id, "content": [
                {"type": "web_search_result", "url": url, "title": title, "encrypted_content": "x", "page_age": None}
                for url, title in results]}]


def message_events(blocks, *, stop_reason: str = "end_turn", model: str = MODEL, input_tokens: int = 1000,
                   output_tokens: int = 500, web_searches: int = 0) -> list[dict]:
    events = [{"type": "message_start", "message": {
        "id": "msg_fake", "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": 1, "cache_creation_input_tokens": 0,
                  "cache_read_input_tokens": 0}}}]
    for index, block in enumerate(blocks):
        if block["type"] == "text":
            events.append({"type": "content_block_start", "index": index,
                           "content_block": {"type": "text", "text": "", "citations": None}})
            for citation in block.get("citations") or []:
                events.append({"type": "content_block_delta", "index": index,
                               "delta": {"type": "citations_delta", "citation": citation}})
            events.append({"type": "content_block_delta", "index": index,
                           "delta": {"type": "text_delta", "text": block["text"]}})
        elif block["type"] == "server_tool_use":
            events.append({"type": "content_block_start", "index": index, "content_block": {**block, "input": {}}})
            events.append({"type": "content_block_delta", "index": index,
                           "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
        else:
            events.append({"type": "content_block_start", "index": index, "content_block": block})
        events.append({"type": "content_block_stop", "index": index})
    usage = {"output_tokens": output_tokens}
    if web_searches:
        usage["server_tool_use"] = {"web_search_requests": web_searches}
    events.append({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                   "usage": usage})
    events.append({"type": "message_stop"})
    return events


def stream(blocks, **kwargs) -> Sse:
    return Sse(message_events(blocks, **kwargs))


class FakeAnthropic:
    def __init__(self, tls: tuple | None = None) -> None:
        self.routes: dict[tuple[str, str], object] = {
            ("GET", f"/v1/models/{MODEL}"): Json(200, model_body())}
        self.queues: dict[tuple[str, str], list] = {}
        self.requests: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # tenang di output tes
                pass

            def _send(self, status: int, payload: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _answer(self):
                path = urlsplit(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                fake.requests.append({"method": self.command, "path": path, "headers": dict(self.headers),
                                      "body": json.loads(raw) if raw else None})
                key = (self.command, path)
                queue = fake.queues.get(key)
                response = queue.pop(0) if queue else fake.routes.get(
                    key, Json(404, error_body("not_found_error", f"Unknown path {path}")))
                if response is DROP:
                    self.close_connection = True
                    return
                if isinstance(response, (Sse, Truncated)):
                    payload = b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode()
                                       for e in response.events)
                    if isinstance(response, Truncated):
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Content-Length", str(len(payload) + 1000))
                        self.end_headers()
                        self.wfile.write(payload)
                        self.wfile.flush()
                        self.close_connection = True
                        return
                    self._send(200, payload, "text/event-stream")
                else:
                    self._send(response.status, json.dumps(response.body).encode(), "application/json")

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

    def set(self, method: str, path: str, response) -> None:
        self.routes[(method, path)] = response

    def queue(self, method: str, path: str, *responses) -> None:
        self.queues.setdefault((method, path), []).extend(responses)

    def messages(self) -> list[dict]:
        """Permintaan POST /v1/messages yang diterima."""
        return [r for r in self.requests if r["method"] == "POST" and r["path"] == "/v1/messages"]

    def __enter__(self) -> FakeAnthropic:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
