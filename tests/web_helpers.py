"""Bantuan tes web app: home berisi data dari fixture rekaman, runner palsu, dan test client."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask.testing import FlaskClient

from etsy_insights.parser import PARSER_VERSION, parse_search
from etsy_insights.runner import RunnerBusy, RunnerStatus
from etsy_insights.store import Store
from tests.test_parser import load_raw

TOKEN = "t" * 32
FIXTURE_KEYWORDS = ["personalized", "sweatshirt", "custom", "swearshirt"]


def seeded_home(home: Path) -> Path:
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / "keywords.txt").write_text("\n".join(FIXTURE_KEYWORDS) + "\n", encoding="utf-8")
    now = datetime.now().astimezone()
    store = Store(home / "data" / "etsy.db")
    store.sync_user_keywords(FIXTURE_KEYWORDS, now)
    for keyword in FIXTURE_KEYWORDS:
        raw = load_raw(keyword)
        parsed = parse_search(raw)
        keyword_id = store.get(keyword).id
        store.save_result(keyword_id, parsed.main, raw, now, PARSER_VERSION)
        store.save_harvest(keyword_id, parsed.related, 200, 2, now)
    store.close()
    return home


class FakeRunner:
    def __init__(self):
        self.started: list[dict] = []
        self.running = False
        self.stopped = False

    def start(self, test_run=False, ignore_cooldown=False):
        if self.running:
            raise RunnerBusy("A session is already running.")
        self.started.append({"test_run": test_run, "ignore_cooldown": ignore_cooldown})
        return Path("session.log")

    def stop(self):
        self.stopped = True
        was_running, self.running = self.running, False
        return was_running

    def status(self, tail=20):
        return RunnerStatus(self.running, "app" if self.running else None, None, 0, None, (), False)


class _Client(FlaskClient):
    def open(self, *args, **kwargs):
        kwargs.setdefault("base_url", "http://127.0.0.1:8765")
        return super().open(*args, **kwargs)


def client(app):
    app.test_client_class = _Client
    return app.test_client()


def printify_app(home: Path, fake, *, spawn=lambda f: f()):
    """App dengan klien Printify yang mengarah ke server Printify palsu (tanpa jeda, tanpa proxy)."""
    from etsy_insights.printify_api import PrintifyClient
    from etsy_insights.web import create_app
    from tests.printify_fake import no_proxy_opener

    def factory(token):
        return PrintifyClient(token, base_url=fake.url, min_interval=0, sleep=lambda s: None, opener=no_proxy_opener())
    app = create_app(home, token=TOKEN, runner=FakeRunner(), printify_client=factory, printify_spawn=spawn)
    return app, client(app)
