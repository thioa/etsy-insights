import os
import subprocess
from pathlib import Path

import pytest

from etsy_insights.browser import connected_browser, ensure_chrome, probe_debug_port

pytestmark = [pytest.mark.smoke,
              pytest.mark.skipif(not os.environ.get("CHROME_SMOKE_PATH"), reason="CHROME_SMOKE_PATH tidak diset")]


def test_real_chrome_attach_and_stays_open(tmp_path):
    port = 9339
    ep = ensure_chrome(port, tmp_path / "prof", Path(os.environ["CHROME_SMOKE_PATH"]),
                       ["--headless=new", "--no-sandbox"])
    try:
        with connected_browser(ep) as context:
            page = context.new_page()
            page.goto("data:text/html,<title>ok</title>")
            assert page.title() == "ok"
            assert page.evaluate("navigator.webdriver") is False
        assert probe_debug_port(port) is not None
    finally:
        subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"])
