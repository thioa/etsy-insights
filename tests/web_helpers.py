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


def printify_app(home: Path, fake, *, spawn=lambda f: f(), port: int = 8765):
    """App dengan klien Printify yang mengarah ke server Printify palsu (tanpa jeda, tanpa proxy)."""
    from etsy_insights.printify_api import PrintifyClient
    from etsy_insights.web import create_app
    from tests.printify_fake import no_proxy_opener

    def factory(token):
        return PrintifyClient(token, base_url=fake.url, min_interval=0, sleep=lambda s: None, opener=no_proxy_opener())
    app = create_app(home, token=TOKEN, runner=FakeRunner(), port=port, printify_client=factory,
                     printify_spawn=spawn)
    return app, client(app)


SWEAT_TITLE = "Unisex Heavy Blend™ Crewneck Sweatshirt"
MUG_TITLE = "Accent Coffee Mug, 11oz"


def seed_printify(home: Path, *, mug_cost: int = 512, mug_shipping: int | None = 699) -> dict[str, int]:
    """Dua jenis produk *own* (tanpa koneksi Printify): sweatshirt 13.50/4.75 dan mug."""
    from etsy_insights.printify_store import PrintifyStore, SyncedType, SyncResult
    store = Store(Path(home) / "data" / "etsy.db")
    try:
        printify = PrintifyStore(store)
        printify.apply_sync(SyncResult(111, "My Etsy Shop", (), (), (
            SyncedType(6, 99, SWEAT_TITLE, "Monster Digital", "own", 1350, 1600, 475, 3, True),
            SyncedType(68, 1, MUG_TITLE, "SPOKE Custom Products", "own", mug_cost, mug_cost, mug_shipping, 2, True),
        )), datetime.now().astimezone())
        ids = {t.title: t.id for t in printify.types()}
        return {"sweatshirt": ids[SWEAT_TITLE], "mug": ids[MUG_TITLE]}
    finally:
        store.close()


def seed_ready_keyword(home: Path, keyword: str = "custom mug") -> str:
    """Hasil pencarian sintetis berlabel Gold/Potential dengan harga pembeli US$15.30–18.70."""
    import dataclasses
    store = Store(Path(home) / "data" / "etsy.db")
    try:
        now = datetime.now().astimezone()
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        def retarget(url: str) -> str:  # respons Etsy dicocokkan lewat parameter `query` di URL
            parts = urlsplit(url)
            query = [(k, keyword if k == "query" else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
            return urlunsplit(parts._replace(query=urlencode(query)))
        original = load_raw("sweatshirt")
        raw = dataclasses.replace(original, keyword=keyword, responses=tuple(
            dataclasses.replace(r, url=retarget(r.url)) for r in original.responses))
        metrics = dataclasses.replace(parse_search(load_raw("sweatshirt")).main, search_volume=1_000_000,
                                      conversion_level=4, competition_value=1)
        if store.get(keyword) is None:
            store.sync_user_keywords([keyword], now)
        store.save_result(store.get(keyword).id, metrics, raw, now, PARSER_VERSION)
        return keyword
    finally:
        store.close()
