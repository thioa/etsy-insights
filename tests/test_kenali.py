"""run_kenali dengan context palsu: penyimpanan saat dihentikan dan pemilihan tab."""
import json
import os

from playwright.sync_api import Error as PlaywrightError

from etsy_insights.recorder import INSIGHTS_URL, run_kenali
from tests.helpers import T0


class FakeTab:
    def __init__(self, ctx, url="about:blank"):
        self.ctx, self.url = ctx, url

    def goto(self, url, wait_until=None):
        self.url = url

    def content(self):
        return "<html>isi</html>"

    def screenshot(self, full_page=False):
        return b"PNG"

    def wait_for_timeout(self, ms):
        self.ctx.waits += 1
        if self.ctx.fail_on_wait == self.ctx.waits:
            raise self.ctx.fail_with


class FakeContext:
    def __init__(self, extra_urls=(), fail_on_wait=None, fail_with=None):
        self.pages = [FakeTab(self, u) for u in extra_urls]
        self.waits, self.fail_on_wait, self.fail_with = 0, fail_on_wait, fail_with

    def on(self, event, handler):
        pass

    def new_page(self):
        tab = FakeTab(self)
        self.pages.insert(0, tab)
        return tab


def pipe_with(text, close=True):
    r, w = os.pipe()
    os.write(w, text.encode())
    if close:
        os.close(w)
    return os.fdopen(r), (None if close else w)


def run(ctx, stdin, tmp_path):
    return run_kenali(ctx, tmp_path, lambda: T0, stdin=stdin, print_fn=lambda *a: None)


def test_kenali_saves_on_ctrl_c(tmp_path):
    stdin, w = pipe_with("\n", close=False)
    path = run(FakeContext(fail_on_wait=2, fail_with=KeyboardInterrupt()), stdin, tmp_path)
    os.close(w)
    assert len(json.loads(path.read_text(encoding="utf-8"))["snapshots"]) == 1


def test_kenali_saves_when_chrome_closed(tmp_path):
    stdin, w = pipe_with("\n", close=False)
    path = run(FakeContext(fail_on_wait=2, fail_with=PlaywrightError("Target page has been closed")), stdin, tmp_path)
    os.close(w)
    assert len(json.loads(path.read_text(encoding="utf-8"))["snapshots"]) == 1


def test_kenali_snapshots_only_insights_tabs(tmp_path):
    stdin, _ = pipe_with("\nselesai\n")
    ctx = FakeContext(extra_urls=("https://www.etsy.com/your/orders/sold", "https://www.google.com/search?q=etsy.com"))
    data = json.loads(run(ctx, stdin, tmp_path).read_text(encoding="utf-8"))
    assert [s["page_url"] for s in data["snapshots"]] == [INSIGHTS_URL]
