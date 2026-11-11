# Etsy Insights — Tahap 4 (Koneksi Printify) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Etsy Insights membaca produk dan katalog Printify pengguna (hanya membaca), mencocokkan
keyword peluang dengan jenis produk, menghitung margin per penjualan, memberi label **Ready to
sell**, dan mengusulkan keyword awal.

**Architecture:**
- Logika murni dipisah per modul: `margin.py` (hitungan sen), `product_words.py` (kamus dan
  pencocokan), `product_fit.py` (gabungan per keyword), dan `printify_suggestions.py`.
- Sisi Printify:
  - `printify_api.py`: klien `GET` dengan stdlib `urllib`;
  - `printify_sync.py`: langkah sync dan `SyncJob` di thread latar web server;
  - `printify_store.py`: tabel di `etsy.db`, satu transaksi per sync;
  - `printify_token.py`: file token `0600`.
- Web: blueprint baru `web/printify.py` + `printify.html`. Opportunities, detail keyword, Settings,
  dan Excel diperluas.

**Tech Stack:** Python 3.11+, Flask 3, SQLite (WAL), openpyxl, pytest, Playwright (smoke). Tidak ada
dependensi baru.

**Spec:** `docs/superpowers/specs/2026-11-11-etsy-insights-printify-design.md`

## Global Constraints

- Semua teks UI berbahasa Inggris; README dan pesan chat berbahasa Indonesia.
- Tidak ada dependensi Python baru. HTTP memakai `urllib`.
- Printify hanya diakses dengan `GET` ke `https://api.printify.com`, header
  `Authorization: Bearer <token>` dan `User-Agent: EtsyInsights/4.0`.
- Jeda minimal 1 detik antar permintaan; timeout 30 detik; 429 → tunggu `Retry-After` (default 60),
  maksimal 3 kali coba ulang; 5xx/jaringan → tunggu 5, 15, 45 detik.
- Token tidak pernah muncul di HTML, JSON, log, Excel, atau rekaman.
- Uang dalam sen USD (int). Fee: `ROUND_HALF_UP`. Harga minimal: `ceil`. Persen: 1 desimal.
- Default: `fee_etsy_persen = 9.5`, `fee_etsy_tetap_usd = 0.45`, `margin_minimum_usd = 5`.
- Perilaku sesi Etsy, kuota, cooldown, dan Chrome tidak berubah sama sekali.
- Tes tidak pernah menghubungi Printify atau Etsy.
- Commit diakhiri baris atribusi dari system reminder; tanpa nama model.

## Review Focus

1. **Respons Printify nyata sedikit berbeda dari dokumentasi** (`tags: null`, `is_enabled` hilang) →
   sync tetap jalan dengan default yang wajar. Field wajib yang hilang → berhenti aman + rekaman.
   Dites di Task 4 `test_tolerant_fields` dan `test_unexpected_shape_stops`.
2. **Token ditempel dengan spasi, baris baru, atau awalan `Bearer `** → disimpan bersih. Dites di
   Task 2 `test_save_load_delete`.
3. **Pengguna mengedit kata produk atau biaya saat sync berjalan** → editan tidak tertimpa. Dites di
   Task 2 `test_edits_during_sync_are_kept`.
4. **Harga bukan USD atau dengan pemisah ribuan** (`Rp 712,738`, `CA$15.30`, `US$1,234.50`) → yang
   bukan USD menjadi *Search to see price*, ribuan terbaca benar. Dites di Task 1 `test_parse_usd`.
5. **Bentuk jamak khas produk POD** (*hoodies*, *beanies*, *onesies*, *t-shirts*, huruf non-ASCII) →
   tetap cocok. Dites di Task 1 `test_normalize` dan `test_whole_words_only`.

---

### Task 1: Hitungan margin dan kata produk (logika murni)

**Files:**
- Create: `etsy_insights/margin.py`, `etsy_insights/product_words.py`
- Test: `tests/test_margin.py`, `tests/test_product_words.py`

**Interfaces:**
- Produces (`margin.py`):
  - `Fees(percent: float, fixed_cents: int)` (frozen dataclass)
  - `Margin(status: str, price_cents: int | None, cost_cents: int | None, shipping_cents: int | None, fee_cents: int | None, margin_cents: int | None, margin_percent: float | None, price_needed_cents: int | None)` (frozen)
  - `NO_MATCH: Margin` (status `"no_match"`, semua angka `None`)
  - `STATUS_TEXT = {"no_match": "No match", "no_price": "Search to see price", "cost_unknown": "Cost unknown", "no_shipping": "No US shipping"}`
  - `parse_usd_cents(text: str | None) -> int | None`
  - `paid_price_cents(low: str | None, high: str | None) -> int | None`
  - `fee_cents(price_cents: int, fees: Fees) -> int`
  - `price_needed_cents(cost_cents: int, shipping_cents: int, fees: Fees, target_cents: int) -> int`
  - `compute(price_cents: int | None, cost_cents: int | None, shipping_cents: int | None, fees: Fees, target_cents: int) -> Margin`
  - `is_ready(label: str, margin: Margin, minimum_cents: int) -> bool`
  - `money(cents: int) -> str`
- Produces (`product_words.py`):
  - `DICTIONARY: tuple[tuple[str, tuple[str, ...]], ...]` (spec §7, urutan tabel)
  - `normalize_words(text: str) -> tuple[str, ...]`
  - `words_for_title(title: str) -> list[str]`
  - `matches(keyword: str, words: Sequence[str]) -> bool`

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_margin.py
from etsy_insights.margin import (NO_MATCH, STATUS_TEXT, Fees, compute, fee_cents, is_ready, money,
                                  paid_price_cents, parse_usd_cents)

FEES = Fees(percent=9.5, fixed_cents=45)


def test_spec_example():
    m = compute(3000, 1241, 475, FEES, 500)
    assert (m.status, m.fee_cents, m.margin_cents, m.margin_percent, m.price_needed_cents) == ("ok", 330, 954, 31.8, 2499)
    assert money(954) == "US$9.54" and money(-332) == "-US$3.32" and money(2499) == "US$24.99"


def test_parse_usd():
    assert parse_usd_cents("US$15.30") == 1530
    assert parse_usd_cents("$1,234.50") == 123450
    assert parse_usd_cents("US$18") == 1800
    for text in (None, "", "Rp 712,738", "€15,30", "CA$15.30", "15.30"):
        assert parse_usd_cents(text) is None


def test_paid_price_midpoint():
    assert paid_price_cents("US$15.30", "US$18.70") == 1700
    assert paid_price_cents("US$15.30", "US$18.71") == 1701  # 1700.5 dibulatkan ke atas
    assert paid_price_cents(None, "US$18.70") == 1870
    assert paid_price_cents("Rp 1", None) is None


def test_fee_rounding_half_up():
    assert fee_cents(1010, FEES) == 96 + 45  # 95.95
    assert fee_cents(1700, FEES) == 162 + 45  # 161.5
    assert fee_cents(1, Fees(50, 0)) == 1


def test_statuses_in_order():
    assert compute(None, None, None, FEES, 500).status == "no_price"
    assert compute(3000, None, 475, FEES, 500).status == "cost_unknown"
    assert compute(3000, 1241, None, FEES, 500).status == "no_shipping"
    assert compute(None, 1241, 475, FEES, 500).price_needed_cents == 2499
    assert NO_MATCH.status == "no_match" and NO_MATCH.margin_cents is None
    assert STATUS_TEXT == {"no_match": "No match", "no_price": "Search to see price",
                           "cost_unknown": "Cost unknown", "no_shipping": "No US shipping"}


def test_negative_margin_and_ready():
    loss = compute(1700, 1350, 475, FEES, 500)
    assert (loss.margin_cents, loss.margin_percent, loss.price_needed_cents) == (-332, -19.5, 2619)
    ok = compute(3000, 1241, 475, FEES, 500)
    assert is_ready("Gold", ok, 500) and is_ready("Potential", ok, 954) and not is_ready("Potential", ok, 955)
    assert not is_ready("Skip", ok, 500) and not is_ready("Gold", loss, 0)
    assert not is_ready("Gold", compute(None, 1241, 475, FEES, 500), 0)
```

```python
# tests/test_product_words.py
from etsy_insights.product_words import DICTIONARY, matches, normalize_words, words_for_title


def test_normalize():
    assert normalize_words("Custom T-Shirts & Mugs!") == ("custom", "t", "shirt", "mug")
    assert normalize_words("glasses boxes dress babies baby tees toys") == (
        "glass", "box", "dress", "babie", "babie", "tee", "toy")
    assert normalize_words("hoodies hoodie hoody beanies onesies") == (
        "hoodie", "hoodie", "hoodie", "beanie", "onesie")
    assert normalize_words("Café_Mugs / gifts™") == ("café", "mug", "gift")


def test_whole_words_only():
    shirt = ["t shirt", "tee", "tshirt", "shirt"]
    assert matches("funny shirt for dad", shirt) and matches("custom t-shirts", shirt)
    assert not matches("crewneck sweatshirt", shirt)
    assert matches("personalized coffee mugs", ["mug", "coffee mug", "cup"])
    assert not matches("mugshot poster", ["mug"])
    assert matches("cute beanies for kids", ["hat", "cap", "beanie"])
    assert not matches("anything", [])


def test_words_for_title():
    assert words_for_title("Unisex Heavy Blend™ Crewneck Sweatshirt") == ["sweatshirt", "crewneck", "crew neck", "jumper"]
    assert words_for_title("Accent Coffee Mug, 11oz") == ["mug", "coffee mug", "cup"]
    assert words_for_title("Unisex Jersey Short Sleeve Tee")[0] == "t shirt"
    assert words_for_title("Kiss-Cut Vinyl Decals") == ["sticker", "decal"]
    assert words_for_title("Something Unusual") == []
    assert DICTIONARY[0] == ("sweatshirt", ("crewneck", "crew neck", "jumper"))
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_margin.py tests/test_product_words.py -q`. Expected: FAIL (modul belum ada).
- [ ] **Step 3: Implementasi `margin.py`**
  - `parse_usd_cents`: cocokkan seluruh teks (setelah `strip`) dengan
    `^(?:US)?\$\s?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{1,2}))?$`. Selain itu `None`.
  - Pembulatan dengan `decimal.Decimal`. Fee: `(price × Decimal(str(percent)) / 100)` →
    `quantize(1, ROUND_HALF_UP)`. Harga minimal: `ceil` dari `Decimal`. Persen: `round(…, 1)`
    dari `Decimal` dengan `ROUND_HALF_UP`.
  - `compute` memeriksa urutan `no_price` → `cost_unknown` → `no_shipping` → `ok`.
    `price_needed_cents` diisi setiap kali biaya dan ongkir diketahui, walaupun harga tidak ada.
  - `is_ready` mengikuti spec §8.4: label Gold atau Potential, status `ok`, dan margin ≥ minimum.
  - `money`: `"US$9.54"`, negatif `"-US$3.32"`.
- [ ] **Step 4: Implementasi `product_words.py`**
  - `DICTIONARY` persis seperti tabel spec §7, dengan urutan yang sama. Entri terakhir
    `("backpack", ())`.
  - `normalize_words`: huruf kecil; `-`, `_`, `/`, `&` → spasi; buang karakter selain huruf/angka/
    spasi (Unicode); pecah; lalu dua langkah bentuk dasar dari spec §7 (jamak, lalu akhiran y).
  - `words_for_title`: untuk setiap entri yang kata utama atau salah satu sinonimnya muncul sebagai
    urutan kata utuh di judul, masukkan kata utama lalu sinonimnya. Pertahankan urutan kamus dan
    buang duplikat.
  - `matches`: benar jika urutan kata ternormalisasi salah satu frasa muncul berurutan di keyword.
- [ ] **Step 5: Jalankan.** Run: `.venv/bin/pytest tests/test_margin.py tests/test_product_words.py -q`. Expected: semua PASS.
- [ ] **Step 6: Commit.** `git add etsy_insights/margin.py etsy_insights/product_words.py tests/test_margin.py tests/test_product_words.py && git commit -m "feat: margin math and product word matching"`

---

### Task 2: Data Printify dan file token

**Files:**
- Create: `etsy_insights/printify_store.py`, `etsy_insights/printify_token.py`
- Modify: `etsy_insights/store.py` (jalankan `PRINTIFY_SCHEMA` di `__init__`; properti `connection`)
- Test: `tests/test_printify_store.py`, `tests/test_printify_token.py`

**Interfaces:**
- Consumes: `product_words.words_for_title` (Task 1).
- Produces (`printify_token.py`):
  - `TOKEN_FILE = "printify-token"`
  - `save_token(home: Path, token: str) -> str` (simpan versi bersih, kembalikan token bersih;
    `ValueError` kalau kosong)
  - `load_token(home: Path) -> str | None`
  - `delete_token(home: Path) -> None`
  - `token_hint(token: str) -> str` (`"…" + 4 karakter terakhir`)
- Produces (`printify_store.py`), semua frozen dataclass:
  - `Blueprint(id: int, title: str, brand: str, model: str)`
  - `SyncedProduct(id: str, blueprint_id: int, print_provider_id: int, title: str, tags: tuple[str, ...], cost_min_cents: int, cost_max_cents: int)`
  - `SyncedType(blueprint_id: int, print_provider_id: int, title: str, provider_title: str | None, source: str, cost_min_cents: int | None, cost_max_cents: int | None, shipping_us_cents: int | None, handling_days: int | None, available: bool)`
  - `SyncResult(shop_id: int, shop_title: str, blueprints: tuple[Blueprint, ...], products: tuple[SyncedProduct, ...], types: tuple[SyncedType, ...])`
  - `ProductType(id: int, blueprint_id: int, print_provider_id: int, title: str, provider_title: str | None, source: str, cost_min_cents: int | None, cost_max_cents: int | None, shipping_us_cents: int | None, handling_days: int | None, words: tuple[str, ...], words_edited: bool, available: bool, synced_at: datetime | None)`
  - `OwnProduct(id: str, type_id: int, title: str, tags: tuple[str, ...], cost_min_cents: int)`
  - `PRINTIFY_SCHEMA: str` (DDL spec §6)
  - `class PrintifyStore(store: Store)` dengan metode:
    - `meta(key: str) -> str | None`, `set_meta(key: str, value: str | None) -> None`
    - `apply_sync(result: SyncResult, now: datetime) -> None`
    - `record_sync_error(message: str) -> None`
    - `types(include_unavailable: bool = True) -> list[ProductType]`, `type(type_id: int) -> ProductType | None`
    - `picked_keys() -> list[tuple[int, int]]`
    - `add_picked(blueprint_id, print_provider_id, title, provider_title, cost_cents, shipping_us_cents, handling_days, now) -> ProductType`
    - `update_type(type_id: int, *, words: Sequence[str] | None = None, cost_cents: int | None = None) -> ProductType`
    - `remove_picked(type_id: int) -> bool`
    - `products() -> list[OwnProduct]`
    - `search_blueprints(query: str, limit: int = 30) -> list[Blueprint]`, `has_blueprints() -> bool`
    - `link(keyword_id: int, type_id: int | None) -> None`, `links() -> dict[str, int]` (teks keyword → type_id)
  - `Store.connection` (properti, koneksi sqlite yang sama)

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tests/test_printify_token.py
import stat

import pytest

from etsy_insights.printify_token import delete_token, load_token, save_token, token_hint


def test_save_load_delete(tmp_path):
    assert save_token(tmp_path, "  Bearer abc.def-123\n") == "abc.def-123"
    assert load_token(tmp_path) == "abc.def-123"
    assert stat.S_IMODE((tmp_path / "printify-token").stat().st_mode) == 0o600
    assert token_hint("abc.def-123") == "…-123"
    delete_token(tmp_path)
    delete_token(tmp_path)
    assert load_token(tmp_path) is None


def test_empty_token_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_token(tmp_path, "  Bearer  ")
```

`tests/test_printify_store.py` memakai helper `result(...)` di dalam file tes yang menyusun
`SyncResult` kecil. Tes berikut wajib ada, masing-masing dengan pernyataan tegas:

- `test_schema_created_by_store`: `Store(tmp/"etsy.db")` → kelima tabel spec §6 ada.
- `test_apply_sync_creates_own_types`: dua produk jenis (6, 99) dengan biaya 1350–1600 dan 1300–1900
  → satu jenis *own* dengan biaya 1300–1900. `words` sama dengan `words_for_title(title)`.
  `products()` berisi 2 produk. `meta("shop_id") == "111"`. `meta("last_sync_at")` terisi.
- `test_apply_sync_rules`, yang mencakup kelima aturan §6:
  - *own* yang hilang tanpa tautan → dihapus;
  - *own* yang hilang dengan tautan → jadi *picked* dengan biaya tetap;
  - *picked* yang muncul sebagai *own* → `source == "own"` dengan biaya sync;
  - *picked* `available=False` → `available` false;
  - `words_edited` tidak ditimpa.
- `test_edits_during_sync_are_kept`: `SyncResult` disusun, lalu `update_type(words=["crewneck"])`,
  lalu `apply_sync` → `words == ("crewneck",)`.
- `test_failed_sync_records_error_only`: `record_sync_error("x")` → `meta("last_sync_error") == "x"`,
  jenis produk tidak berubah. `apply_sync` berikutnya mengosongkan error.
- `test_picked_crud_and_links`:
  - `add_picked` → `source == "picked"`, `words` dari judul;
  - `update_type(cost_cents=1250)` mengubah biaya;
  - `remove_picked(own_id)` → `False`;
  - `remove_picked(picked_id)` → `True`, dan tautannya ikut terhapus;
  - `link(kid, tid)` lalu `links() == {"sweatshirt": tid}`; `link(kid, None)` → `{}`.
- `test_search_blueprints`: tidak membedakan huruf besar/kecil atas judul, brand, dan model; maksimal
  `limit`; `has_blueprints()` false sebelum sync.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_printify_store.py tests/test_printify_token.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi `printify_token.py`**
  - Buang spasi; buang awalan `Bearer ` (tidak membedakan huruf besar/kecil); buang spasi lagi.
  - Tulis ke file sementara di folder yang sama dengan `os.open(..., 0o600)`, lalu `os.replace`.
- [ ] **Step 4: Implementasi `printify_store.py` dan hook di `store.py`**
  - `store.py` mengimpor `PRINTIFY_SCHEMA` dan menjalankannya setelah `_SCHEMA`. `printify_store.py`
    hanya mengimpor `Store` di bawah `TYPE_CHECKING`, supaya tidak ada impor melingkar.
  - `apply_sync` berjalan di `BEGIN IMMEDIATE … COMMIT`, dengan `ROLLBACK` saat exception. Keadaan
    terkini (`words_edited`, biaya *picked*, tautan) dibaca di dalam transaksi itu juga.
  - `words_json` diisi `words_for_title(title)` untuk jenis baru, atau saat `words_edited = 0`.
  - `update_type(words=…)` menormalkan spasi, membuang yang kosong, dan menyetel `words_edited = 1`.
- [ ] **Step 5: Jalankan.** Run: `.venv/bin/pytest tests/test_printify_store.py tests/test_printify_token.py tests/test_store.py -q`. Expected: semua PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: Printify tables, sync rules and token file"`

---

### Task 3: Klien API Printify

**Files:**
- Create: `etsy_insights/printify_api.py`, `tests/printify_fake.py`, `tests/printify_data.py`
- Test: `tests/test_printify_api.py`

**Interfaces:**
- Produces (`printify_api.py`):
  - `BASE_URL = "https://api.printify.com"`, `USER_AGENT = "EtsyInsights/4.0"`
  - Exception (semua punya `.message`, teks UI dari spec §12):
    - `PrintifyError(Exception)` (induk);
    - `TokenRejected`;
    - `MissingScope(scope: str)`;
    - `PrintifyBusy`;
    - `PrintifyUnreachable`;
    - `UnexpectedResponse(path: str, body: str)`.
  - `class PrintifyClient(token: str, *, base_url: str = BASE_URL, min_interval: float = 1.0, timeout: float = 30, clock=time.monotonic, sleep=time.sleep, opener: urllib.request.OpenerDirector | None = None)` dengan metode:
    - `get(path: str, params: dict | None = None) -> Any`
    - `shops() -> list[dict]`
    - `products(shop_id: int) -> list[dict]` (semua halaman, `limit=50`)
    - `blueprints() -> list[dict]`
    - `providers(blueprint_id: int) -> list[dict]`
    - `shipping(blueprint_id: int, provider_id: int) -> dict`
- Produces (tes):
  - `printify_fake.FakePrintify`: server HTTP lokal di thread, dipakai sebagai context manager.
    - `.url`
    - `.set(path, body, status=200, headers=None)`
    - `.queue(path, *responses)`: respons berurutan; setiap respons berupa `(status, body, headers)`.
    - `.requests`: daftar `(method, path, query, headers)`.
    - `.load_default()`: memuat semua data `printify_data`.
  - `printify_fake.no_proxy_opener()`
  - `printify_data`: `SHOPS`, `BLUEPRINTS`, `PRODUCTS_PAGE_1`, `PRODUCTS_PAGE_2`, `PROVIDERS`
    (dict per blueprint_id), `SHIPPING` (dict per `(blueprint_id, provider_id)`). Isinya:
    - `SHOPS`: `[{"id": 111, "title": "My Etsy Shop", "sales_channel": "etsy"}, {"id": 222, "title": "API store", "sales_channel": "custom_integration"}]`
    - `BLUEPRINTS`: (6, "Unisex Heavy Blend™ Crewneck Sweatshirt", "Gildan", "18000"),
      (68, "Accent Coffee Mug, 11oz", "Generic brand", ""), (384, "Unisex Jersey Short Sleeve Tee",
      "Bella+Canvas", "3001")
    - Halaman 1 (`current_page` 1, `last_page` 2): produk `"p-sweat"` (6, 99), tags
      `["Mom Gift", "custom sweatshirt"]`, varian `{1: 1350 aktif, 2: 1600 aktif, 3: 900 tidak aktif}`
    - Halaman 2: produk `"p-mug"` (68, 1), tags `["mom gift", "coffee lover"]`, varian `{10: 512 aktif}`;
      produk `"p-off"` (384, 29) tanpa varian aktif
    - `PROVIDERS`: `{6: [{"id": 99, "title": "Monster Digital"}], 68: [{"id": 1, "title": "SPOKE Custom Products"}], 384: [{"id": 29, "title": "Monster Digital"}]}`
    - `SHIPPING[(6, 99)]`: `handling_time` 3 hari; profil US (varian 1, 2, 3) `first_item` 475 USD;
      profil `REST_OF_THE_WORLD` 1100
    - `SHIPPING[(68, 1)]`: hanya profil `REST_OF_THE_WORLD` 699 USD
    - `SHIPPING[(384, 29)]`: hanya profil `["CA"]` 899 USD

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_printify_api.py`). Setiap tes membuat klien dengan
  `opener=no_proxy_opener()`, jam palsu (`t = [0.0]`, `clock=lambda: t[0]`), dan
  `sleep=lambda s: (sleeps.append(s), t.__setitem__(0, t[0] + s))`.
  - `test_sends_auth_and_user_agent`: `shops()` → `SHOPS`. Request: `GET /v1/shops.json`,
    `Authorization: Bearer tok`, `User-Agent: EtsyInsights/4.0`.
  - `test_products_reads_all_pages`: `products(111)` → 3 produk. Query berisi `page=1&limit=50`
    lalu `page=2&limit=50`.
  - `test_waits_between_requests`: dua panggilan tanpa waktu berlalu → `sleeps == [1.0]`.
  - `test_429_uses_retry_after`: antrean `429 (Retry-After: 7)`, lalu `200` → hasil benar dan
    `7 in sleeps`.
  - `test_429_gives_up_after_three_retries`: 4× `429` tanpa header → `PrintifyBusy`.
    `sleeps.count(60) == 3`. `.message == "Printify is busy. Try Sync again in a few minutes."`
  - `test_server_errors_back_off`: 4× `500` → `PrintifyUnreachable`. Jeda coba ulang
    `[5, 15, 45]` (setelah membuang jeda 1 detik). `.message == "Could not reach Printify. Check your internet connection and try again."`
  - `test_401_and_403`:
    - `401` → `TokenRejected`, `.message == "Printify rejected the token. Create a new token in Printify and paste it here."`
    - `403` pada `/v1/shops/111/products.json` → `MissingScope`, `.scope == "products.read"`,
      `.message == "The token needs the products.read permission. Create a new token with shops.read, products.read and catalog.read."`
    - `403` pada `/v1/catalog/...` → `catalog.read`; pada `/v1/shops.json` → `shops.read`.
  - `test_not_json_is_unexpected`: `200` dengan body `"oops"` → `UnexpectedResponse`, `.path` dan
    `.body` terisi.
  - `test_connection_refused_is_unreachable`: base URL ke port yang tidak dipakai → `PrintifyUnreachable`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_printify_api.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi `printify_api.py`** dan `tests/printify_fake.py` / `printify_data.py`.
  - Pemetaan scope 403 berdasarkan path: `/v1/shops.json` → `shops.read`; `/v1/shops/` →
    `products.read`; `/v1/catalog/` → `catalog.read`.
  - Timeout dan `URLError` diperlakukan seperti 5xx.
  - Respons dibaca sebagai JSON `utf-8`.
  - Tidak ada metode selain `GET`.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_printify_api.py -q`. Expected: semua PASS, total < 5 detik.
- [ ] **Step 5: Commit.** `git commit -m "feat: read-only Printify API client with pacing and retries"`

---

### Task 4: Sync Printify

**Files:**
- Create: `etsy_insights/printify_sync.py`
- Test: `tests/test_printify_sync.py`

**Interfaces:**
- Consumes: `PrintifyClient` dan exception-nya (Task 3), `PrintifyStore` + `SyncResult` (Task 2),
  `load_token` (Task 2).
- Produces:
  - `NeedShopChoice(PrintifyError)` dengan `.shops: list[dict]`, `.message == "Choose the Printify shop that is connected to your Etsy shop."`
  - `choose_shop(shops: list[dict], saved_shop_id: int | None) -> dict`
  - `us_shipping_cents(shipping: dict, variant_id: int | None) -> int | None`
  - `handling_days(shipping: dict) -> int | None`
  - `build_result(client: PrintifyClient, shop: dict, picked: Sequence[tuple[int, int]], progress: Callable[[str, int, int], None]) -> SyncResult`
  - `record_unexpected(home: Path, exc: UnexpectedResponse, now: datetime) -> Path`
  - `class SyncJob(home: Path, client_factory: Callable[[str], PrintifyClient], *, now: Callable[[], datetime] = …, spawn: Callable[[Callable[[], None]], None] = <daemon thread>)` dengan metode:
    - `start() -> None`: `SyncBusy` kalau sedang berjalan; `NotConnected` kalau tidak ada token.
    - `run_now() -> None`: dijalankan oleh `spawn`; tidak pernah melempar exception.
    - `status() -> dict`: `{"state", "step", "done", "total", "error", "last_sync_at", "shops"}`.
      `state` ∈ `idle | running | choose_shop | error | done`.
  - `SyncBusy` (`.message == "A sync is already running."`), `NotConnected` (`.message == "Connect Printify first."`)

- [ ] **Step 1: Tulis tes yang gagal** (memakai `FakePrintify.load_default()` dan klien tanpa jeda).
  - `test_choose_shop`:
    - satu toko `etsy` → toko itu;
    - `saved_shop_id=222` → toko 222;
    - dua toko `etsy` → `NeedShopChoice` dengan `.shops` berisi keduanya;
    - tidak ada toko `etsy` → `NeedShopChoice`.
  - `test_us_shipping_rules`:
    - `SHIPPING[(6, 99)]` dengan varian 1 → 475;
    - `(68, 1)` → 699 (fallback rest of the world);
    - `(384, 29)` → `None`;
    - currency `"EUR"` → `None`;
    - `variant_id=None` → `first_item` terkecil di antara profil yang berlaku untuk AS;
    - `handling_days(SHIPPING[(6, 99)]) == 3`.
  - `test_build_result_from_fixtures`, dengan `picked=[(384, 29), (999, 5)]`:
    - *own* (6, 99): biaya 1350–1600, ongkir 475, waktu produksi 3, provider "Monster Digital",
      judul dari katalog;
    - *own* (68, 1): biaya 512–512, ongkir 699;
    - `p-off` dilewati;
    - *picked* (384, 29): `available=True`, ongkir `None`;
    - *picked* (999, 5): `available=False`, dan tidak ada request untuk blueprint 999;
    - 3 blueprint;
    - urutan progres naik sampai `done == total`.
  - `test_tolerant_fields`: `tags: null` → `()`. Varian tanpa `is_enabled` dianggap aktif.
  - `test_unexpected_shape_stops`: produk tanpa `variants` → `UnexpectedResponse`.
  - `test_job_success`: token tersimpan → `start()` dengan `spawn=lambda f: f()` →
    `status()["state"] == "done"`. Store punya 2 jenis *own*, dan `last_sync_at` terisi.
  - `test_job_errors_keep_old_data`: sync sukses, lalu fake mengembalikan `401` → `state == "error"`.
    `error` adalah pesan `TokenRejected`, `meta("last_sync_error")` sama, dan jenis produk lama masih ada.
  - `test_job_unexpected_records_without_token`: `/v1/catalog/blueprints.json` mengembalikan `"oops"`
    →
    - ada file `rekaman/printify-*.json` yang berisi path dan body;
    - token tidak ada di file;
    - `error == "Printify sent data in an unexpected format. Sync stopped and nothing was changed. Send this file to Claude: <path>"`.
  - `test_job_choose_shop`: dua toko `etsy` → `state == "choose_shop"` dan `shops` berisi `id`,
    `title`, `sales_channel`. Setelah `set_meta("shop_id", "111")` → sync berikutnya `done`.
  - `test_job_busy_and_not_connected`: tanpa token → `NotConnected`; saat `state == "running"` →
    `SyncBusy`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_printify_sync.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi `printify_sync.py`**
  - Langkah dan urutan progres:
    `"Reading shops"` → `"Reading your products"` → `"Reading the catalog"` →
    `"Reading shipping ({n} of {m})"`.
  - `build_result` memvalidasi bentuk respons. Field wajib yang hilang atau bertipe salah →
    `UnexpectedResponse(path, json.dumps(item)[:2000])`.
  - Biaya *own* = min/max `cost` varian aktif di semua produk jenis itu. Untuk `us_shipping_cents`,
    dipakai ID varian aktif termurah.
  - `SyncJob.run_now` membuka `Store` sendiri di thread-nya dan menutupnya di `finally`. Semua
    `PrintifyError` → `state "error"` + `record_sync_error`. Exception lain →
    `"Unexpected error: {Type}: {msg}"`, juga dicatat.
  - Rekaman berisi `{"path", "body", "recorded_at"}` saja.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_printify_sync.py tests/test_printify_store.py -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: Printify sync job with shop choice, shipping rules and safe failure"`

---

### Task 5: Pengaturan fee dan margin

**Files:**
- Modify: `etsy_insights/config.py`, `etsy_insights/settings.py`, `config.toml`
- Test: `tests/test_config.py`, `tests/test_settings.py`

**Interfaces:**
- Produces:
  - `Config.fee_etsy_persen: float = 9.5`, `Config.fee_etsy_tetap_usd: float = 0.45`,
    `Config.margin_minimum_usd: float = 5.0`
  - `_FLOAT_KEYS` berisi ketiganya. `_RANGE_OR_DEFAULT` ditambah `(0, 30)`, `(0, 5)`, `(0, 100)`.
  - `settings.FORM_FIELDS` ditambah `"fee_etsy_persen", "fee_etsy_tetap_usd", "margin_minimum_usd"`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
# tambahan tests/test_config.py
def test_selling_defaults_and_limits(tmp_path):
    cfg = Config()
    assert (cfg.fee_etsy_persen, cfg.fee_etsy_tetap_usd, cfg.margin_minimum_usd) == (9.5, 0.45, 5.0)
    path = tmp_path / "config.toml"
    path.write_text("fee_etsy_persen = 45\nfee_etsy_tetap_usd = 0.3\nmargin_minimum_usd = 7.5\n")
    cfg, warnings = load_config(path)
    assert (cfg.fee_etsy_persen, cfg.fee_etsy_tetap_usd, cfg.margin_minimum_usd) == (9.5, 0.3, 7.5)
    assert any("fee_etsy_persen" in w for w in warnings)
```

```python
# tambahan tests/test_settings.py
def test_selling_fields_saved_and_validated(tmp_path):
    form = settings_form(Config()) | {"fee_etsy_persen": "6.5", "fee_etsy_tetap_usd": "0.25", "margin_minimum_usd": "4"}
    cfg, errors = save_settings(tmp_path, form)
    assert errors == {} and (cfg.fee_etsy_persen, cfg.fee_etsy_tetap_usd, cfg.margin_minimum_usd) == (6.5, 0.25, 4.0)
    bad = form | {"fee_etsy_persen": "31", "fee_etsy_tetap_usd": "x", "margin_minimum_usd": "101"}
    cfg, errors = save_settings(tmp_path, bad)
    assert cfg is None and errors == {"fee_etsy_persen": "Enter a percentage from 0 to 30.",
                                      "fee_etsy_tetap_usd": "Enter an amount from 0 to 5.",
                                      "margin_minimum_usd": "Enter an amount from 0 to 100."}
```

  `test_shipped_config_is_rendered_default` dan `test_shipped_config_equals_defaults` yang sudah ada
  harus tetap lulus setelah `config.toml` diperbarui.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_config.py tests/test_settings.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi**
  - `_parse_scalar`: kunci di `_FLOAT_KEYS` dikembalikan sebagai `float`.
  - `render_config` menulis blok berikut tepat sebelum `[bobot]`:

```
# Etsy fees as a percentage of the sale price (transaction + payment processing). Check your Shop Manager.
fee_etsy_persen = 9.5

# Fixed Etsy fees per sale in US$ (payment processing + listing fee).
fee_etsy_tetap_usd = 0.45

# A keyword is "Ready to sell" when the estimated margin per sale is at least this many US$.
margin_minimum_usd = 5
```

  - Tulis ulang `config.toml` dengan `render_config(Config())`.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_config.py tests/test_settings.py tests/test_cli.py -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: Etsy fee and minimum margin settings"`

---

### Task 6: Kecocokan produk per keyword dan usulan keyword

**Files:**
- Create: `etsy_insights/product_fit.py`, `etsy_insights/printify_suggestions.py`
- Modify: `etsy_insights/store.py` (`keyword_texts`)
- Test: `tests/test_product_fit.py`, `tests/test_printify_suggestions.py`

**Interfaces:**
- Consumes: `margin` (Task 1), `product_words.matches` (Task 1), `ProductType`/`OwnProduct` (Task 2),
  field Config (Task 5), `ScoredKeyword` (`score.py`), `TasteProfile.paid_price_low/high` (`taste.py`).
- Produces (`product_fit.py`):
  - `Candidate(type: ProductType, margin: Margin)`
  - `ProductFit(primary: ProductType | None, margin: Margin, candidates: tuple[Candidate, ...], ready: bool, linked: bool)`
  - `fees_from_config(cfg: Config) -> Fees` dan `minimum_cents(cfg: Config) -> int` (pembulatan
    `round(usd × 100)`)
  - `fit_keyword(keyword: str, label: str, price_cents: int | None, types: Sequence[ProductType], linked_type_id: int | None, fees: Fees, minimum: int) -> ProductFit`
  - `fit_all(scored: Sequence[ScoredKeyword], profiles: Mapping[str, TasteProfile], types: Sequence[ProductType], links: Mapping[str, int], cfg: Config) -> dict[str, ProductFit]`
  - `match_counts(keywords: Iterable[str], types: Sequence[ProductType], links: Mapping[str, int]) -> dict[int, int]`
- Produces (`printify_suggestions.py`):
  - `Suggestion(keyword: str, origin: str)`
  - `suggest(types: Sequence[ProductType], products: Sequence[OwnProduct], existing: Collection[str], limit: int = 100) -> list[Suggestion]`
- Produces (`store.py`): `Store.keyword_texts() -> set[str]` (semua keyword, status apa pun)

- [ ] **Step 1: Tulis tes yang gagal.** Tes membuat `ProductType` langsung dengan helper `pt(id,
  title, source, cost, ship, words, available=True)`.
  - `test_best_margin_wins_and_ties_prefer_own`:
    - Keyword "custom sweatshirt" dengan harga 3000.
    - Jenis A *picked* biaya 1241/ongkir 475, jenis B *own* biaya 1241/ongkir 475, jenis C *own*
      biaya 1500. Ketiganya punya kata `sweatshirt`.
    - Hasil: `primary` = B (seri dengan A, *own* menang); `margin.margin_cents == 954`;
      `candidates` berisi 3.
  - `test_no_match_and_unavailable`:
    - "gift for mom" → `margin is NO_MATCH`, `primary is None`.
    - Jenis cocok yang `available=False` diabaikan.
  - `test_link_overrides_automatic`: keyword "gift for mom" ditautkan ke mug → hanya kandidat mug,
    dan `linked is True`.
  - `test_no_price_picks_own_then_cheapest`: harga `None` → status `no_price`; `primary` = jenis
    *own* termurah.
  - `test_ready_follows_label`: margin 954 dan minimum 500 → `ready` untuk "Gold", tidak untuk "Skip".
  - `test_fit_all_uses_profile_price_and_config`:
    - `profiles["sweatshirt"].paid_price_low/high == "US$15.30"/"US$18.70"`, biaya 1350, ongkir 475,
      Config default.
    - Hasil: margin −332 dan `price_needed_cents == 2619`.
    - Keyword tanpa profil → `no_price`.
  - `test_match_counts`: `["custom sweatshirt", "sweatshirts", "mug", "gift"]` dengan tautan
    `{"gift": mug_id}` → `{sweat_id: 2, mug_id: 2}`.
  - `tests/test_printify_suggestions.py::test_suggestions_order_and_dedupe`:
    - Jenis sweatshirt (`words[0] == "sweatshirt"`), jenis mug, dan poster `available=False`.
    - Tags produk: `["Mom Gift", "custom sweatshirt"]` dan `["mom gift", "coffee lover"]`.
    - `existing={"custom sweatshirt", "mug"}`.
    - Hasil `[(s.keyword, s.origin)]` ==
      `[("mom gift", "tag on 2 products"), ("coffee lover", "tag on 1 product"), ("custom mug", "product word"), ("personalized mug", "product word"), ("personalized sweatshirt", "product word"), ("sweatshirt", "product word")]`.
    - `limit=2` → dua pertama.
  - `test_keyword_texts` (di `tests/test_store.py`): keyword `pending` dan `harvested` sama-sama
    muncul.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_product_fit.py tests/test_printify_suggestions.py tests/test_store.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai spec §7–§9.
  - **Kata utama** = `words[0]` dari jenis produk itu. Jenis tanpa kata tidak menghasilkan usulan.
  - **Urutan kandidat:**
    - yang berstatus `ok` dulu, margin tertinggi;
    - lalu *own* sebelum *picked*;
    - lalu biaya terendah (`None` terakhir);
    - lalu `id`.
  - **Tautan ke jenis yang tidak tersedia** → `NO_MATCH`.
  - **Performa:** `fit_all` menormalkan setiap keyword sekali, dan `matches` menerima tuple yang
    sudah ternormalisasi lewat fungsi internal. Tujuannya supaya 30 ribu keyword × 20 jenis tetap
    cepat.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_product_fit.py tests/test_printify_suggestions.py tests/test_store.py -q`. Expected: semua PASS.
- [ ] **Step 5: Ukur.** Jalankan `scratchpad/perf2.py` (dari tahap 3), diperluas dengan 20 jenis
  produk: `fit_all` atas sekitar 30 ribu keyword harus < 0,5 detik. Kalau lebih, tambahkan cache
  sesuai spec §4 dan ledger sebagai ruling.
- [ ] **Step 6: Commit.** `git commit -m "feat: product fit per keyword and seed keyword suggestions"`

---

### Task 7: Halaman dan API Printify

**Files:**
- Create: `etsy_insights/web/printify.py`, `etsy_insights/web/templates/printify.html`
- Modify:
  - `etsy_insights/web/__init__.py` (`create_app(…, printify_client=None, printify_spawn=None)`,
    `ctx().printify_job`, mendaftarkan blueprint);
  - `etsy_insights/web/templates/base.html` (menu Printify);
  - `etsy_insights/web/static/app.js`, `app.css`.
- Test: `tests/test_web_printify.py`; `tests/web_helpers.py` (helper `printify_app(home, fake)`)

**Interfaces:**
- Consumes: Task 2–6.
- Produces:
  - Endpoint spec §11, persis. Nama, isi, dan kode status:
    - `token`: `200 {"shops": [...]}` atau `400 {"error"}`;
    - `sync`: `202` atau `409 {"error"}`;
    - `status`: `200 SyncJob.status()`;
    - `catalog`: `200 {"results": [{"id", "title", "brand", "model"}]}` atau
      `409 {"error": "Run Sync once to search the catalog."}`;
    - `providers`: `200 {"providers": [{"id", "title"}]}`;
    - `types/*`, `link`, `suggestions/add`: `200 {"ok": true}` atau `400 {"error"}` / `404`.
  - `create_app(home, *, token, runner, port=8765, now=None, on_quit=None, printify_client: Callable[[str], PrintifyClient] | None = None, printify_spawn=None)`

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_web_printify.py`, Printify palsu + `spawn=lambda f: f()`):
  - `test_page_not_connected`: `/printify` berisi `"Connect Printify"`,
    `"Paste your Printify token"`, `"shops.read"`, `"products.read"`, `"catalog.read"`. Menu berisi
    `href="/printify"`.
  - `test_token_saved_after_test`: `POST /api/printify/token {"token": "secret-tok-9876"}` → `200`
    dengan daftar toko. File token ada. Halaman berisi `"token ends …9876"` dan `"Never synced"`.
  - `test_bad_token_not_saved`: fake `401` → `400` dengan pesan `TokenRejected`. File token tidak ada.
  - `test_sync_and_types_table`: `POST /api/printify/sync` → `202`, lalu status `done`. Halaman berisi
    `"Your product"`, `"US$13.50"`, `"US$4.75"`, `"Monster Digital"`, dan kolom `Matches`.
  - `test_sync_conflicts`:
    - belum terhubung → `409 "Connect Printify first."`;
    - job `running` → `409 "A sync is already running."`
  - `test_choose_shop_flow`: dua toko `etsy` → halaman berisi `"Use this shop"`.
    `POST /api/printify/shop {"shop_id": 111}` → `200`, lalu sync `done`.
  - `test_catalog_and_providers`:
    - sebelum sync → `409 "Run Sync once to search the catalog."`;
    - setelah sync, `q=mug` → blueprint 68;
    - `providers?blueprint_id=6` → `[{"id": 99, "title": "Monster Digital"}]`.
  - `test_picked_types_api`:
    - `types/add {blueprint_id: 384, print_provider_id: 29, cost_usd: "12.50"}` → biaya 1250, ongkir `None`;
    - `cost_usd: "0"` → `400 "Enter an amount from 0.01 to 500."`;
    - `types/update` kata `"tee, t shirt"` → `words_edited`;
    - `types/update` biaya untuk *own* → `400 "Cost can only be set for picked product types."`;
    - `types/remove` *own* → `400`; *picked* → `200`.
  - `test_link_api`:
    - `link {"keyword": "sweatshirt", "type_id": X}` → tersimpan;
    - `type_id: null` → dihapus;
    - keyword tidak dikenal → `404`.
  - `test_suggestions_add`: `suggestions/add {"keywords": ["mom gift"]}` → `"mom gift"` ada di
    `keywords.txt`, dan halaman Printify tidak lagi mengusulkannya.
  - `test_token_never_leaks`: setelah token disimpan dan sync, token tidak ada di body:
    - `/`, `/printify`, `/opportunities`, `/settings`;
    - `/api/status`, `/api/printify/status`;
    - `/download/excel` (bytes xlsx);
    - log `caplog`.
  - `test_new_posts_need_app_token`: setiap path `POST` §11 tanpa header `X-App-Token` → `403`.
  - `test_page_states`:
    - job `running` dengan `step="Reading your products", done=1, total=4` → halaman berisi
      `"Syncing… Reading your products (1 of 4)"`;
    - setelah sync gagal → pesan error tampil di bawah kartu;
    - jenis tanpa kata → `"Add product words"`;
    - *picked* `available=False` → `"No longer available"`.
  - `test_disconnect_keeps_data`: `disconnect` → file token hilang, halaman berisi `"Connect Printify"`,
    dan tabel jenis produk tetap tampil.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_printify.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** halaman sesuai spec §10 (kartu koneksi, Product types, Add from
  catalog, Suggested keywords) dan API §11.
  - **JS:** form token dan tombol baris memakai `form[data-api]` / `button[data-api]` yang sudah ada.
  - **JS baru (kecil):**
    - polling `/api/printify/status` setiap 2 detik selama `state == "running"` dengan pola
      `setTimeout`; reload halaman saat `done`, `error`, atau `choose_shop`;
    - pencarian katalog;
    - pilihan provider;
    - **Add selected** untuk usulan.
  - **Biaya** di form dalam US$ teks. Validasi `0.01–500`, lalu dikonversi ke sen dengan
    `parse_usd_cents("$" + text)`.
  - **Matches** memakai `match_counts` atas `store.latest_results()`.
  - **Waktu** sync tampil dalam waktu lokal (`astimezone()`), format `%Y-%m-%d %H:%M`.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_web_printify.py tests/test_web_api.py tests/test_web_pages.py -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: Printify page and API (connect, sync, product types, suggestions)"`

---

### Task 8: Opportunities, detail keyword, Settings, dan Excel

**Files:**
- Modify:
  - `etsy_insights/web/views.py`;
  - templates `opportunities.html`, `keyword.html`, `settings.html`;
  - `etsy_insights/web/api.py` (download Excel);
  - `etsy_insights/export.py`.
- Test: `tests/test_web_pages.py`, `tests/test_export.py`; `tests/web_helpers.py`
  (`seed_printify`, `seed_ready_keyword`)

**Interfaces:**
- Consumes: `fit_all`, `ProductFit` (Task 6), `PrintifyStore` (Task 2), field Config (Task 5).
- Produces:
  - `export_excel(..., fits: Mapping[str, ProductFit] | None = None)`. Kolom baru setelah
    `"Entry difficulty"`: `"Printify product"`, `"Est. margin (USD)"`, `"Margin %"`, `"Ready to sell"`.
  - `seed_printify(home, *, mug_cost: int = 512, mug_shipping: int | None = 699) -> dict[str, int]`:
    memasang lewat `apply_sync` dua jenis *own*:
    - sweatshirt (6, 99): biaya 1350–1600, ongkir 475;
    - mug (68, 1): biaya `mug_cost`, ongkir `mug_shipping`.

    Mengembalikan `{"sweatshirt": id, "mug": id}`.
  - `seed_ready_keyword(home, keyword: str = "custom mug") -> str`. Semua keyword hasil pencarian di
    fixture berlabel Skip, jadi helper ini menyimpan hasil pencarian sintetis untuk `keyword`:
    - raw dari `load_raw("sweatshirt")`, jadi harga yang dibayar pembeli US$15.30–18.70;
    - metrik `dataclasses.replace(...)` dari fixture sweatshirt dengan `search_volume=1_000_000`,
      `conversion_level=4`, `competition_value=1`, sehingga labelnya Gold/Potential.

- [ ] **Step 1: Tulis tes yang gagal**
  - `test_opportunities_product_and_margin`: setelah `seed_printify`, baris `sweatshirt` berisi
    `"Unisex Heavy Blend"`, `"-US$3.32"`, dan class margin `bad`. Baris yang tidak cocok berisi
    `"No match"`. Keyword hasil panen yang cocok berisi `"Search to see price"`.
  - `test_ready_filter_and_margin_sort`:
    - Jalankan `seed_ready_keyword(home)` dan `seed_printify(home, mug_cost=100, mug_shipping=0)`.
      Margin "custom mug" = 1700 − 100 − 0 − 207 = 1393.
    - `/opportunities?ready=1` berisi `"custom mug"` dan `"US$13.93 · 81.9%"`, dan tidak berisi
      `"sweatshirt"`. Chip `"Ready to sell"` aktif.
    - `sort=margin&dir=desc`: baris dengan margin diketahui berurutan menurun; yang belum
      diketahui ada di bawah.
  - `test_keyword_detail_printify_panel`: `/keyword/sweatshirt` berisi `"Printify"`,
    `"Unisex Heavy Blend"`, `"US$13.50"`, `"US$4.75"`, `"US$2.07"` (fee), `"-US$3.32"`,
    `"Price needed for a $5 margin"`, `"US$26.19"`, dan dropdown `"Link to product type"` dengan
    opsi `"Automatic"`.
  - `test_keyword_detail_search_to_see_price`: keyword hasil panen yang cocok sweatshirt →
    `"Search to see price"` dan tombol **Prioritize**.
  - `test_settings_selling_section`: `/settings` berisi `"Selling on Etsy"`,
    `"Etsy fees (% of sale)"`, `"Fixed fee per sale (US$)"`, `"Minimum margin (US$)"`.
  - `test_excel_printify_columns` (`tests/test_export.py`): header sheet Opportunities berakhir
    dengan keempat kolom baru. Baris sweatshirt berisi judul jenis, `-3.32`, `-19.5`, dan `""`;
    keyword yang ready berisi `"Yes"`. Tanpa `fits`, kolomnya kosong.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_pages.py tests/test_export.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi**
  - **`views.Row`** ditambah:
    - `product: str`;
    - `margin_text: str`: `"US$9.54 · 31.8%"` atau teks status;
    - `margin_class: str`: `good` jika ≥ minimum, `ok` jika 0 ≤ margin < minimum, `bad` jika
      negatif, `unknown` jika tidak ada;
    - `ready: bool`.
  - **`opportunities`:** parameter `ready=1`, dan `SORT_KEYS["margin"]` dengan baris tanpa margin
    selalu di bawah.
  - **Detail:** teks `"Price needed for a ${min} margin"`. `${min}` ditulis tanpa `.00` kalau bulat
    (`$5`), selain itu dua desimal (`$5.50`).
  - **Dropdown tautan:** memanggil `POST /api/printify/link`.
  - **Settings:** bagian **Selling on Etsy** dengan tiga isian dan pesan error dari Task 5.
  - **Excel:** `api.download_excel` memberi `fits`.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: product and margin in opportunities, keyword detail, settings and Excel"`

---

### Task 9: Smoke test, README, dan paket 4.0.0

**Files:**
- Modify: `tests/test_web_smoke.py`, `README.md`, `macos/README.txt`
- Test: `tests/test_web_smoke.py::test_printify_end_to_end` (marker `smoke`)

- [ ] **Step 1: Tulis smoke test yang gagal**:
  - Server sungguhan (`make_server`), `create_app` dengan `printify_client` yang mengarah ke
    `FakePrintify`, dan Chromium.
  - Buka `/printify` → isi token → klik **Test and save** → klik **Sync now** → tunggu teks
    `"Your product"` (≤ 10 detik).
  - Siapkan keyword ready dengan `seed_ready_keyword(home)`. Fake memakai biaya mug 100 dan
    ongkir 0 (`FakePrintify.set` dengan varian dan profil ongkir yang diubah).
  - Buka `/opportunities?ready=1` → teks `"Ready to sell"` dan keyword itu terlihat.
  - Pastikan tidak ada request ke host selain `127.0.0.1`.
- [ ] **Step 2: Jalankan, pastikan gagal lalu lulus setelah perbaikan kecil yang diperlukan.** Run: `CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`. Expected: semua PASS.
- [ ] **Step 3: README** (bahasa Indonesia), bagian baru **Printify**:
  - membuat token (My Profile → Connections, tiga izin baca);
  - menempel token dan Sync;
  - arti kolom Product/Margin dan Ready to sell;
  - menambahkan jenis produk dari katalog dan mengisi biaya;
  - Suggested keywords;
  - pengaturan fee (cocokkan dengan Shop Manager);
  - catatan bahwa aplikasi hanya membaca dan tidak bisa mengubah toko Printify.

  `macos/README.txt` mendapat dua baris ringkas.
- [ ] **Step 4: Semua tes + paket.** Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke && .venv/bin/python -m tools.build_app 4.0.0 && zipinfo dist/Etsy-Insights.zip | grep "MacOS/etsy-insights"`. Expected: semua PASS; `-rwxr-xr-x`.
- [ ] **Step 5: Commit dan salin paket.** `git commit -m "feat: Printify smoke test, README and 4.0.0 package"`, lalu `cp dist/Etsy-Insights.zip /home/user/`.
