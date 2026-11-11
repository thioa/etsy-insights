"""Sync Printify: membaca toko, produk, katalog, dan ongkir, lalu menyimpannya sekaligus (spec Tahap 4 §5–§6).

Sync berjalan di thread latar web server (`SyncJob`). Kalau gagal di mana pun, data lama tidak berubah.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .printify_api import PrintifyClient, PrintifyError, UnexpectedResponse
from .printify_store import Blueprint, PrintifyStore, SyncedProduct, SyncedType, SyncResult
from .printify_token import load_token
from .store import Store

Progress = Callable[[str, int, int], None]


class NeedShopChoice(PrintifyError):
    message = "Choose the Printify shop that is connected to your Etsy shop."

    def __init__(self, shops: list[dict]) -> None:
        self.shops = shops
        super().__init__()


class SyncBusy(PrintifyError):
    message = "A sync is already running."


class NotConnected(PrintifyError):
    message = "Connect Printify first."


def _bad(path: str, value: Any) -> UnexpectedResponse:
    return UnexpectedResponse(path, json.dumps(value, default=str)[:2000])


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def choose_shop(shops: list[dict], saved_shop_id: int | None) -> dict:
    if saved_shop_id is not None:
        for shop in shops:
            if shop.get("id") == saved_shop_id:
                return shop
    etsy = [s for s in shops if str(s.get("sales_channel", "")).lower() == "etsy"]
    if len(etsy) == 1:
        return etsy[0]
    raise NeedShopChoice(etsy or list(shops))


def _profiles(shipping: dict) -> list[dict]:
    profiles = shipping.get("profiles")
    return profiles if isinstance(profiles, list) else []


def us_shipping_cents(shipping: dict, variant_id: int | None) -> int | None:
    """Ongkir item pertama ke AS (sen USD). Profil US dulu, lalu REST_OF_THE_WORLD."""
    applicable = [p for p in _profiles(shipping)
                  if variant_id is None or variant_id in (p.get("variant_ids") or [])]
    for country in ("US", "REST_OF_THE_WORLD"):
        matching = [p for p in applicable if country in (p.get("countries") or [])]
        if matching:
            costs = [p["first_item"]["cost"] for p in matching
                     if isinstance(p.get("first_item"), dict) and p["first_item"].get("currency") == "USD"
                     and _int(p["first_item"].get("cost"))]
            return min(costs) if costs else None
    return None


def handling_days(shipping: dict) -> int | None:
    handling = shipping.get("handling_time")
    value = handling.get("value") if isinstance(handling, dict) else None
    return value if _int(value) else None


def _check_shipping(path: str, shipping: dict) -> None:
    for profile in _profiles(shipping):
        first = profile.get("first_item") if isinstance(profile, dict) else None
        if (not isinstance(profile, dict) or not isinstance(profile.get("countries"), list)
                or not isinstance(first, dict) or not _int(first.get("cost"))):
            raise _bad(path, shipping)
    if not isinstance(shipping.get("profiles"), list):
        raise _bad(path, shipping)


def _product(item: Any, path: str) -> tuple[SyncedProduct, int] | None:
    """(produk, ID varian aktif termurah), atau None kalau tidak ada varian aktif."""
    if not isinstance(item, dict):
        raise _bad(path, item)
    pid, title, variants = item.get("id"), item.get("title"), item.get("variants")
    blueprint_id, provider_id = item.get("blueprint_id"), item.get("print_provider_id")
    if (not isinstance(pid, (str, int)) or not isinstance(title, str) or not isinstance(variants, list)
            or not _int(blueprint_id) or not _int(provider_id)):
        raise _bad(path, item)
    enabled = []
    for v in variants:
        if not isinstance(v, dict) or not _int(v.get("id")) or not _int(v.get("cost")):
            raise _bad(path, item)
        if v.get("is_enabled", True):
            enabled.append(v)
    if not enabled:
        return None
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        raise _bad(path, item)
    costs = [v["cost"] for v in enabled]
    cheapest = min(enabled, key=lambda v: v["cost"])
    return (SyncedProduct(str(pid), blueprint_id, provider_id, title, tuple(str(t) for t in tags),
                          min(costs), max(costs)), cheapest["id"])


def _type_details(client: PrintifyClient, key: tuple[int, int], title: str, provider_title: str | None,
                  products: list[SyncedProduct], cheapest: dict[tuple[int, int], tuple[int, int]]) -> SyncedType:
    blueprint_id, provider_id = key
    is_own = key in cheapest
    if not is_own and provider_title is None:  # provider tidak ada lagi di katalog
        return SyncedType(*key, title, None, "picked", None, None, None, None, False)
    shipping = client.shipping(blueprint_id, provider_id)
    _check_shipping(f"/v1/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/shipping.json", shipping)
    if not is_own:
        return SyncedType(*key, title, provider_title, "picked", None, None, us_shipping_cents(shipping, None),
                          handling_days(shipping), True)
    own = [p for p in products if (p.blueprint_id, p.print_provider_id) == key]
    return SyncedType(*key, title, provider_title, "own", min(p.cost_min_cents for p in own),
                      max(p.cost_max_cents for p in own), us_shipping_cents(shipping, cheapest[key][1]),
                      handling_days(shipping), True)


def build_result(client: PrintifyClient, shop: dict, picked: Sequence[tuple[int, int]],
                 progress: Progress) -> SyncResult:
    if not _int(shop.get("id")) or not isinstance(shop.get("title"), str):
        raise _bad("/v1/shops.json", shop)
    shop_id = shop["id"]

    progress("Reading your products", 0, 0)
    products_path = f"/v1/shops/{shop_id}/products.json"
    products: list[SyncedProduct] = []
    cheapest: dict[tuple[int, int], tuple[int, int]] = {}  # jenis → (biaya, varian)
    for item in client.products(shop_id):
        parsed = _product(item, products_path)
        if parsed is None:
            continue
        product, variant_id = parsed
        products.append(product)
        key = (product.blueprint_id, product.print_provider_id)
        if key not in cheapest or product.cost_min_cents < cheapest[key][0]:
            cheapest[key] = (product.cost_min_cents, variant_id)

    progress("Reading the catalog", 0, 0)
    blueprints: dict[int, Blueprint] = {}
    for item in client.blueprints():
        if not isinstance(item, dict) or not _int(item.get("id")) or not isinstance(item.get("title"), str):
            raise _bad("/v1/catalog/blueprints.json", item)
        blueprints[item["id"]] = Blueprint(item["id"], item["title"], str(item.get("brand") or ""),
                                           str(item.get("model") or ""))

    own_keys = list(dict.fromkeys((p.blueprint_id, p.print_provider_id) for p in products))
    picked_keys = [k for k in dict.fromkeys(picked) if k not in cheapest]
    detail_keys = own_keys + [k for k in picked_keys if k[0] in blueprints]
    providers: dict[int, dict[int, str]] = {}
    types: list[SyncedType] = []
    for index, key in enumerate(detail_keys, start=1):
        progress(f"Reading shipping ({index} of {len(detail_keys)})", index - 1, len(detail_keys))
        blueprint_id, provider_id = key
        if blueprint_id not in providers:
            path = f"/v1/catalog/blueprints/{blueprint_id}/print_providers.json"
            names = {}
            for item in client.providers(blueprint_id):
                if not isinstance(item, dict) or not _int(item.get("id")):
                    raise _bad(path, item)
                names[item["id"]] = str(item.get("title") or "")
            providers[blueprint_id] = names
        title = blueprints[blueprint_id].title if blueprint_id in blueprints else ""
        provider_title = providers[blueprint_id].get(provider_id)
        types.append(_type_details(client, key, title, provider_title, products, cheapest))
        progress(f"Reading shipping ({index} of {len(detail_keys)})", index, len(detail_keys))
    for key in picked_keys:
        if key[0] not in blueprints:
            types.append(SyncedType(*key, "", None, "picked", None, None, None, None, False))
    return SyncResult(shop_id, shop["title"], tuple(blueprints.values()), tuple(products), tuple(types))


def record_unexpected(home: Path, exc: UnexpectedResponse, now: datetime) -> Path:
    folder = Path(home) / "rekaman"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"printify-{now:%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps({"path": exc.path, "body": exc.body, "recorded_at": now.isoformat()},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="printify-sync", daemon=True).start()


class SyncJob:
    def __init__(self, home: Path, client_factory: Callable[[str], PrintifyClient], *,
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
                 spawn: Callable[[Callable[[], None]], None] = _thread) -> None:
        self._home = Path(home)
        self._client_factory = client_factory
        self._now = now
        self._spawn = spawn
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"state": "idle", "step": "", "done": 0, "total": 0, "error": None, "shops": []}

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._state.update(changes)

    def _db_path(self) -> Path:
        return self._home / "data" / "etsy.db"

    def start(self) -> None:
        if not load_token(self._home):
            raise NotConnected()
        with self._lock:
            if self._state["state"] == "running":
                raise SyncBusy()
            self._state.update(state="running", step="Starting", done=0, total=0, error=None, shops=[])
        self._spawn(self.run_now)

    def run_now(self) -> None:
        store = None
        try:
            token = load_token(self._home)
            if not token:
                raise NotConnected()
            store = Store(self._db_path())
            printify = PrintifyStore(store)
            client = self._client_factory(token)
            self._set(step="Reading shops")
            shops = client.shops()
            saved = printify.meta("shop_id")
            shop = choose_shop(shops, int(saved) if saved and saved.isdigit() else None)
            result = build_result(client, shop, printify.picked_keys(),
                                  lambda step, done, total: self._set(step=step, done=done, total=total))
            printify.apply_sync(result, self._now())
            self._set(state="done", step="", error=None)
        except NeedShopChoice as exc:
            shops = [{"id": s.get("id"), "title": s.get("title"), "sales_channel": s.get("sales_channel")}
                     for s in exc.shops]
            self._set(state="choose_shop", error=exc.message, shops=shops)
        except UnexpectedResponse as exc:
            recording = record_unexpected(self._home, exc, self._now())
            self._fail(store, f"{exc.message} Sync stopped and nothing was changed. "
                              f"Send this file to Claude: {recording}")
        except PrintifyError as exc:
            self._fail(store, exc.message)
        except Exception as exc:  # noqa: BLE001 - selalu tampilkan pesan yang bisa dibaca
            self._fail(store, f"Unexpected error: {type(exc).__name__}: {exc}")
        finally:
            if store is not None:
                store.close()

    def _fail(self, store: Store | None, message: str) -> None:
        if store is not None:
            try:
                PrintifyStore(store).record_sync_error(message)
            except Exception:  # noqa: BLE001 - pesan tetap tampil di halaman
                pass
        self._set(state="error", error=message)

    def status(self) -> dict:
        with self._lock:
            status = dict(self._state, shops=list(self._state["shops"]))
        last_sync_at = None
        if self._db_path().exists():
            store = Store(self._db_path())
            try:
                printify = PrintifyStore(store)
                last_sync_at = printify.meta("last_sync_at")
                if status["state"] == "idle" and status["error"] is None:
                    status["error"] = printify.meta("last_sync_error")
            finally:
                store.close()
        status["last_sync_at"] = last_sync_at
        return status
