import json
import os
import subprocess
from pathlib import Path

import pytest

from etsy_insights.browser import connected_browser, ensure_chrome
from etsy_insights.recorder import INSIGHTS_URL, run_kenali
from tests.helpers import T0

pytestmark = [pytest.mark.smoke,
              pytest.mark.skipif(not os.environ.get("CHROME_SMOKE_PATH"), reason="CHROME_SMOKE_PATH tidak diset")]

FAKE_PAGE = """<html><head><meta name="csrf_nonce" content="rahasia"></head><body>
<h1>Insights palsu</h1><script>fetch('/api/v3/ajax/insights?q=boho').then(r => r.json())</script></body></html>"""


def test_kenali_records_routed_etsy_traffic(tmp_path):
    port = 9341
    ep = ensure_chrome(port, tmp_path / "prof", Path(os.environ["CHROME_SMOKE_PATH"]),
                       ["--headless=new", "--no-sandbox"])
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"\nselesai\n")
    os.close(write_fd)
    try:
        with connected_browser(ep) as context:
            context.route(INSIGHTS_URL, lambda route: route.fulfill(status=200, content_type="text/html",
                                                                    body=FAKE_PAGE))
            context.route("https://www.etsy.com/api/v3/ajax/**", lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"volume": 1200, "csrf_token": "s3"}'))
            with os.fdopen(read_fd) as stdin:
                path = run_kenali(context, tmp_path / "rekaman", lambda: T0, stdin=stdin, print_fn=lambda *a: None)
    finally:
        subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"])
    data = json.loads(path.read_text(encoding="utf-8"))
    bodies = [r["body"] for r in data["responses"]]
    assert {"volume": 1200, "csrf_token": "[DIHAPUS]"} in bodies
    assert len(data["snapshots"]) == 1 and "rahasia" not in data["snapshots"][0]["html"]
