"""Web app lokal Etsy Insights (Flask)."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, g

from ..config import Config, load_config
from ..printify_api import PrintifyClient
from ..printify_sync import SyncJob
from ..store import Store
from . import security


def _default_quit() -> None:
    threading.Timer(0.5, os._exit, [0]).start()


def create_app(home: Path, *, token: str, runner, port: int = 8765,
               now: Callable[[], datetime] | None = None, on_quit: Callable[[], None] | None = None,
               printify_client: Callable[[str], PrintifyClient] | None = None,
               printify_spawn: Callable[[Callable[[], None]], None] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(APP_TOKEN=token, APP_HOME=Path(home), APP_PORT=port)
    clock = now or (lambda: datetime.now().astimezone())
    client_factory = printify_client or PrintifyClient
    job_options = {"spawn": printify_spawn} if printify_spawn is not None else {}
    app.extensions["etsy"] = SimpleNamespace(
        runner=runner, now=clock, on_quit=on_quit or _default_quit, cache={},
        printify_client=client_factory,
        printify_job=SyncJob(Path(home), client_factory, now=clock, **job_options))
    security.install(app, port)

    from . import api, catalog, printify, views
    app.register_blueprint(api.bp)
    app.register_blueprint(views.bp)
    app.register_blueprint(printify.bp)
    app.register_blueprint(catalog.bp)

    @app.teardown_appcontext
    def close_store(exc):
        store = g.pop("store", None)
        if store is not None:
            store.close()

    return app


def ctx() -> SimpleNamespace:
    from flask import current_app
    return current_app.extensions["etsy"]


def home() -> Path:
    from flask import current_app
    return current_app.config["APP_HOME"]


def get_store() -> Store:
    if "store" not in g:
        g.store = Store(home() / "data" / "etsy.db")
    return g.store


def get_config() -> Config:
    return load_config(home() / "config.toml")[0]
