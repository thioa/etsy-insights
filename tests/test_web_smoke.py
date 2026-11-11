"""Server HTTP sungguhan (werkzeug) + SessionRunner dengan sesi tiruan."""
import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from werkzeug.serving import make_server

from etsy_insights.runner import SessionRunner
from etsy_insights.web import create_app
from tests.web_helpers import TOKEN, seeded_home

FAKE = [sys.executable, str(Path(__file__).parent / "fake_session.py")]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"X-App-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def test_real_server_start_and_stop(tmp_path):
    port = free_port()
    home = seeded_home(tmp_path / "home")
    app = create_app(home, token=TOKEN, runner=SessionRunner(home, command=FAKE), port=port)
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert call(port, "/api/ping") == {"ok": True, "app": "etsy-insights"}
        assert call(port, "/api/session/start", {"test_run": True}) == {"ok": True}
        end = time.monotonic() + 5
        while call(port, "/api/status")["runner"]["current_keyword"] != "beta":
            assert time.monotonic() < end
            time.sleep(0.1)
        call(port, "/api/session/stop", {})
        end = time.monotonic() + 5
        while call(port, "/api/status")["runner"]["running"]:
            assert time.monotonic() < end
            time.sleep(0.1)
    finally:
        server.shutdown()
