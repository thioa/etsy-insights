# Etsy Insights — Tahap 5 (Katalog Printify) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menu **Catalog** menampilkan semua produk Printify per kategori, dengan foto dan ringkasan
peluang Etsy. Ada tombol **Research** untuk mengantrekan keyword awal kategori, dan halaman kategori
untuk memilih provider lalu menambahkan model ke Product types.

**Architecture:**
- Kategori dihitung dari judul blueprint dengan kamus kata produk yang diperluas (`product_words.py`).
- `catalog.py` menyusun kategori, ringkasan peluang, status Research, serta detail provider dan ongkir
  (dengan cache 30 hari di `printify_store.py`).
- Blueprint web baru `web/catalog.py` menyajikan dua halaman dan dua endpoint. Endpoint Printify Tahap 4
  ikut memakai cache.

**Tech Stack:** Python 3.11+, Flask 3, SQLite (WAL), pytest, Playwright (smoke). Tidak ada dependensi baru.

**Spec:** `docs/superpowers/specs/2026-11-11-etsy-insights-printify-catalog-design.md`

## Global Constraints

- Semua teks UI berbahasa Inggris; README dan pesan chat berbahasa Indonesia.
- Printify tetap hanya `GET`. Token Printify tidak pernah sampai ke browser.
- `/api/catalog/shipping` dan `/api/printify/providers` wajib `X-App-Token`. Endpoint `POST` memakai
  perlindungan yang ada.
- Hanya alamat gambar yang diawali `https://` yang dipakai.
- Cache provider dan ongkir berlaku 30 hari. Kegagalan Printify tidak disimpan.
- Research tidak mengubah kuota, jeda, atau aturan sesi Etsy.
- Tes tidak pernah menghubungi Printify atau Etsy.
- Commit diakhiri baris atribusi dari system reminder; tanpa nama model.

## Review Focus

1. **Judul katalog yang "kotor"** (™, ukuran, warna dalam kurung, tanda hubung, huruf besar) → kategori
   tetap benar. Dites di Task 1 `test_categories_for_catalog_titles`.
2. **Kategori yang sebagian modelnya tanpa foto, atau dengan alamat foto bukan `https`** → kartu memakai
   foto pertama yang sah, atau *No photo*. Dites di Task 3 `test_category_photo_skips_missing`.
3. **Keyword awal yang sudah ada sebagai hasil panen** → ikut diriset dan dipindah ke depan antrean, bukan
   dianggap *Researched*. Dites di Task 3 `test_research_state_and_harvested_seeds`.
4. **Database dari versi 4.x** (tabel `printify_blueprints` tanpa kolom `image_url`) → terbuka tanpa error,
   katalog tampil dengan *No photo*. Dites di Task 2 `test_old_database_gets_image_column`.
5. **Pencarian katalog dengan huruf besar atau tanda baca** (`q=Necklace!`) → tetap menemukan kategorinya.
   Dites di Task 5 `test_catalog_search_and_filters`.

---

### Task 1: Kamus diperluas dan kategori

**Files:**
- Modify: `etsy_insights/product_words.py`
- Test: `tests/test_categories.py` (baru); `tests/test_product_words.py` tetap lulus

**Interfaces:**
- Produces:
  - `DICTIONARY`: 52 entri, urutan Tahap 4 lalu tabel spec §5.
  - `ENTRIES: dict[str, tuple[str, ...]]`: kata utama → (kata utama, sinonim…).
  - `CATEGORY_NAMES: dict[str, str]`: semua kata utama + `"other"` → nama tampilan (spec §5).
  - `category_for(title: str) -> str`: kata utama, atau `"other"`.
  - `category_slug(main: str) -> str`: `"wall clock"` → `"wall-clock"`.
  - `category_from_slug(slug: str) -> str | None`: kebalikannya; `None` kalau tidak dikenal.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_categories.py`)

```python
import pytest

from etsy_insights.product_words import (CATEGORY_NAMES, DICTIONARY, ENTRIES, category_for, category_from_slug,
                                         category_slug)

TITLES = {
    "Unisex Heavy Blend™ Crewneck Sweatshirt": "sweatshirt",
    "Unisex Heavy Blend™ Hooded Sweatshirt": "hoodie",
    "Unisex Jersey Short Sleeve Tee": "t shirt",
    "Unisex Jersey Long Sleeve Tee": "long sleeve shirt",
    "Unisex Pique Polo Shirt": "polo",
    "Women's Flowy Racerback Tank": "tank top",
    "Unisex Fleece Joggers": "sweatpants",
    "Women's Cut & Sew Casual Leggings (AOP)": "leggings",
    "Accent Coffee Mug, 11oz": "mug",
    "Ceramic Mug 15oz (Black)": "mug",
    "Stainless Steel Travel Mug": "tumbler",
    "Tumbler 20oz": "tumbler",
    "Stainless Steel Water Bottle, Standard Lid": "water bottle",
    "Wine Glass, 12oz": "wine glass",
    "Can Cooler Sleeve": "can cooler",
    "Cotton Canvas Tote Bag": "tote bag",
    "Backpack": "backpack",
    "Laptop Sleeve": "laptop sleeve",
    "Tough Phone Cases": "phone case",
    "Classic Leather Wallet": "wallet",
    "Matte Vertical Posters": "poster",
    "Canvas Gallery Wraps": "canvas",
    "Velveteen Plush Blanket": "blanket",
    "Spun Polyester Square Pillow": "pillow",
    "Wall Clock": "wall clock",
    "Area Rugs": "rug",
    "Beach Towel": "towel",
    "Shower Curtains": "shower curtain",
    "Doormat": "doormat",
    "Indoor Wall Tapestries": "tapestry",
    "Garden & House Banner": "other",
    "Garden Flag": "flag",
    "Bamboo Cutting Board": "cutting board",
    "Scented Soy Candle, 9oz": "candle",
    "Cork Back Coaster": "coaster",
    "Kiss-Cut Stickers": "sticker",
    "Ceramic Ornament, 4 Shapes": "ornament",
    "Heart Necklace": "necklace",
    "Engraved Bar Bracelet": "bracelet",
    "Stud Earrings": "earrings",
    "Acrylic Keychain": "keychain",
    "Greeting Cards (1, 10, 30, and 50pcs)": "greeting card",
    "Postcard Bundles (envelopes not included)": "postcard",
    "Wall Calendars (2027)": "calendar",
    "Spiral Notebook - Ruled Line": "notebook",
    "Jigsaw puzzle with Tin": "puzzle",
    "Mouse Pad (Rectangle)": "mouse pad",
    "Pet Bandana Collar": "pet bandana",
    "Pet Bowl": "pet bowl",
    "Pet Bed": "pet bed",
    "Baby Bib": "bib",
    "Infant Fine Jersey Bodysuit": "other",
    "Something Unusual": "other",
}


@pytest.mark.parametrize("title,expected", TITLES.items())
def test_categories_for_catalog_titles(title, expected):
    assert category_for(title) == expected


def test_dictionary_and_names():
    assert len(DICTIONARY) == 52 and DICTIONARY[0][0] == "sweatshirt" and DICTIONARY[-1][0] == "can cooler"
    assert set(CATEGORY_NAMES) == set(ENTRIES) | {"other"}
    assert (CATEGORY_NAMES["t shirt"], CATEGORY_NAMES["wall clock"], CATEGORY_NAMES["other"]) == (
        "T-shirts", "Wall clocks", "Other")
    assert ENTRIES["necklace"] == ("necklace", "pendant", "name necklace")


def test_slugs_round_trip():
    for main in CATEGORY_NAMES:
        assert category_from_slug(category_slug(main)) == main
    assert category_slug("wall clock") == "wall-clock" and category_from_slug("nope") is None
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_categories.py -q`. Expected: FAIL (nama belum ada).
- [ ] **Step 3: Implementasi**
  - Tambahkan 29 entri spec §5 ke `DICTIONARY` dalam urutan tabel spec. Tulis `CATEGORY_NAMES`
    persis seperti daftar spec §5. Buat `ENTRIES` dari `DICTIONARY`.
  - `category_for` memakai `words_for_title(title)[0]` kalau ada, selain itu `"other"`.
  - Kalau sebuah judul di `TITLES` gagal karena aturan Tahap 4 (misalnya "Garden & House Banner"
    seharusnya `"other"`), sesuaikan kamus, bukan tesnya, lalu ledger sebagai ruling.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_categories.py tests/test_product_words.py tests/test_product_fit.py -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: larger product dictionary and catalog categories"`

---

### Task 2: Foto blueprint dan cache detail

**Files:**
- Modify: `etsy_insights/printify_store.py`, `etsy_insights/store.py` (memanggil migrasi Printify),
  `etsy_insights/printify_sync.py`, `tests/printify_data.py`
- Test: `tests/test_printify_store.py`, `tests/test_printify_sync.py`

**Interfaces:**
- Produces (`printify_store.py`):
  - `Blueprint(id, title, brand, model, image_url: str = "")`
  - `CACHE_MAX_AGE = timedelta(days=30)`
  - `ShippingInfo(shipping_us_cents: int | None, handling_days: int | None)` (frozen dataclass)
  - `migrate_printify(connection) -> None`: tambah kolom `image_url TEXT` ke `printify_blueprints` kalau
    belum ada. Dipanggil `Store.__init__` setelah `PRINTIFY_SCHEMA`.
  - Metode `PrintifyStore`:
    - `blueprints() -> list[Blueprint]` (urut judul)
    - `cached_providers(blueprint_id, now) -> list[tuple[int, str]] | None`
    - `save_providers(blueprint_id, providers, now)`
    - `cached_shipping(blueprint_id, provider_id, now) -> ShippingInfo | None`
    - `save_shipping(blueprint_id, provider_id, info, now)`
  - `blueprint()` dan `search_blueprints()` ikut mengisi `image_url`.
- Produces (`printify_sync.py`): `image_url_from(images: object) -> str`, yaitu string pertama yang
  diawali `https://`, atau `""`.

- [ ] **Step 1: Tulis tes yang gagal**
  - `test_old_database_gets_image_column` (`tests/test_printify_store.py`):
    - buat `printify_blueprints` dengan DDL lama (tanpa `image_url`) lewat `sqlite3`, isi satu baris;
    - `Store(path)` terbuka tanpa error;
    - `PrintifyStore(...).blueprints()[0].image_url == ""`.
  - `test_blueprint_images_saved`: `apply_sync` dengan `Blueprint(6, …, image_url="https://images.printify.com/a.png")`
    → `blueprints()[0].image_url` sama, dan `search_blueprints("sweat")[0].image_url` sama.
  - `test_details_cache`:
    - `save_providers(6, [(99, "Monster Digital")], now)` → `cached_providers(6, now + 29 hari) == [(99, "Monster Digital")]`;
    - `cached_providers(6, now + 31 hari) is None`;
    - `save_shipping(6, 99, ShippingInfo(None, 3), now)` → `cached_shipping(6, 99, now) == ShippingInfo(None, 3)`;
    - `cached_shipping(6, 1, now) is None`.
  - `test_image_url_from` (`tests/test_printify_sync.py`):
    - `["http://x/a.png", "https://x/b.png"]` → `"https://x/b.png"`;
    - `None`, `[]`, `[1, "javascript:x"]` → `""`.
  - `test_build_result_keeps_images`: `printify_data.BLUEPRINTS[0]["images"] = ["https://images.printify.com/sweat.png"]`
    → `Blueprint` id 6 di `SyncResult` membawa alamat itu.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_printify_store.py tests/test_printify_sync.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi**
  - `PRINTIFY_SCHEMA`:
    - `image_url TEXT` ada di DDL `printify_blueprints` untuk database baru;
    - dua tabel cache persis seperti spec §7.
  - Waktu disimpan dengan `_ts` yang ada. Umur dihitung `now - fetched_at <= CACHE_MAX_AGE`.
  - `save_providers` mengganti semua baris blueprint itu.
  - `apply_sync` menyimpan `image_url`.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_printify_store.py tests/test_printify_sync.py tests/test_store.py -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: catalog photos and cached provider/shipping details"`

---

### Task 3: Kategori, ringkasan peluang, dan Research (`catalog.py`)

**Files:**
- Create: `etsy_insights/catalog.py`
- Modify: `etsy_insights/store.py` (`keyword_statuses`), `tests/web_helpers.py` (`CATALOG_BLUEPRINTS`,
  parameter `blueprints` pada `seed_printify`)
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes:
  - `ENTRIES`, `CATEGORY_NAMES`, `category_for`, `category_slug` (Task 1);
  - `Blueprint`, `PrintifyStore` (Task 2);
  - `score_all`, `fits_for_store`, `normalize_words`;
  - `keywords.add_keywords`.
- Produces:
  - `Store.keyword_statuses() -> dict[str, str]` (keyword → status)
  - `CategoryInfo(main: str, slug: str, name: str, blueprints: tuple[Blueprint, ...], photo: str)`.
    `photo` = `image_url` pertama yang tidak kosong menurut urutan judul, atau `""`.
  - `categories_from(blueprints: Sequence[Blueprint]) -> dict[str, CategoryInfo]` (kunci kata utama,
    termasuk `"other"` kalau ada)
  - `ResearchState(status: str, pending: int)`: `status` ∈ `available | in_queue | researched | none`
    (`none` untuk *Other*)
  - `research_seeds(main: str) -> list[str]`
  - `research_state(statuses: Mapping[str, str], main: str) -> ResearchState`
  - `research(home, store, main, now) -> list[str]`: keyword yang dikirim ke `add_keywords`
  - `CategorySummary`: field spec §6 + `info: CategoryInfo` + `research: ResearchState`
    (`most_searched: tuple[str, int] | None`, `best: tuple[str, float, str] | None`, `ready: int | None`)
  - `summarize(store, cfg, categories: Mapping[str, CategoryInfo]) -> dict[str, CategorySummary]`
  - `sort_summaries(summaries: Iterable[CategorySummary], sort: str) -> list[CategorySummary]`
    (`best | searched | products | name`; *Other* selalu terakhir)
  - `top_keywords(store, cfg, main: str, limit: int = 10) -> list[ScoredKeyword]`
  - Tes: `web_helpers.CATALOG_BLUEPRINTS`, yaitu blueprint 6 (sweatshirt,
    `image_url="https://images.printify.com/sweat.png"`), 68 (mug, tanpa foto), 384 (tee), 1000
    ("Heart Necklace"), dan 2000 ("Something Unusual").
    `seed_printify(home, *, mug_cost=512, mug_shipping=699, blueprints=CATALOG_BLUEPRINTS)` ikut
    menyimpannya.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_catalog.py`). Data uji memakai `seeded_home`,
  `seed_printify`, `seed_ready_keyword` dari `tests/web_helpers.py`, ditambah blueprint yang disimpan
  lewat `apply_sync`. Tes wajib:
  - `test_categories_from_groups_by_head_noun`: blueprint sweatshirt, hoodie, dua mug, dan "Something
    Unusual" → kunci `{"sweatshirt", "hoodie", "mug", "other"}`; `categories["mug"].name == "Mugs"` dan
    berisi 2 blueprint; `slug == "mug"`.
  - `test_category_photo_skips_missing`: mug pertama `image_url=""`, kedua `"https://x/b.png"` →
    `photo == "https://x/b.png"`. Kalau tidak ada foto sama sekali → `""`.
  - `test_research_state_and_harvested_seeds`:
    - `research_seeds("necklace") == ["necklace", "custom necklace", "personalized necklace"]`;
    - `statuses = {}` → `available`;
    - `{"necklace": "harvested", "custom necklace": "done", "personalized necklace": "done"}` → `available`;
    - `research(...)` pada keadaan itu mengirim `["necklace", "personalized necklace"]` kalau
      "personalized necklace" belum ada, dan "necklace" lalu berstatus `pending`;
    - semua `pending`/`in_progress` → `in_queue` dengan `pending == 3`;
    - semua `done`/`no_data` → `researched`;
    - `research_state(..., "other").status == "none"`.
  - `test_summary_for_fixture_data`: setelah `seed_ready_keyword(home)` dan
    `seed_printify(home, mug_cost=100, mug_shipping=0)`:
    - `summaries["sweatshirt"]`:
      - `status == "researched"` dan `searched >= 1`;
      - `most_searched[0]` adalah keyword sweatshirt dengan volume tertinggi di fixture;
      - `ready == 0`;
      - `in_my_products is True`.
    - `summaries["mug"].ready == 1` (custom mug).
    - Kategori tanpa keyword → `status == "not_researched"`, `most_searched is None`, `ready is None`.
    - Kategori yang hanya punya keyword panen → `harvested_only`.
  - `test_sort_orders`:
    - `best` mengutamakan `gold + potential`, lalu skor `best`, lalu yang punya data, lalu nama;
    - `name`, `products`, `searched` sesuai field;
    - *Other* selalu terakhir.
  - `test_top_keywords`: maksimal `limit`, urut skor menurun, semuanya cocok kata kategori.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_catalog.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi**
  - Pencocokan keyword ↔ kategori memakai satu indeks frasa untuk semua kategori, dengan pola
    `product_fit._Matcher`. Setiap keyword dinormalkan sekali. `scored` dan `fits` (`fits_for_store`)
    dihitung sekali per panggilan `summarize`.
  - `searched` dihitung dari `keyword_statuses()`, yaitu status `done` atau `no_data`.
  - `ready` = `None` kalau tidak ada jenis produk `available` dengan biaya yang `category_for(title)`-nya
    kategori ini; selain itu jumlah `fits[kw].ready`.
- [ ] **Step 4: Jalankan dan ukur.**
  - Run: `.venv/bin/pytest tests/test_catalog.py -q`. Expected: semua PASS.
  - Ukur `summarize` dengan skrip performa Tahap 4 (30 ribu keyword, 52 kategori). Expected < 0,5 detik.
    Kalau lebih, optimalkan dan ledger.
- [ ] **Step 5: Commit.** `git commit -m "feat: catalog categories, demand summaries and research"`

---

### Task 4: API katalog dan cache detail

**Files:**
- Create: `etsy_insights/web/catalog.py` (blueprint `bp`, bagian API)
- Modify: `etsy_insights/catalog.py` (`provider_list`, `shipping_for`), `etsy_insights/web/printify.py`
  (`providers`, `add_type` memakai cache), `etsy_insights/web/__init__.py` (daftarkan blueprint)
- Test: `tests/test_web_catalog_api.py`

**Interfaces:**
- Consumes: Task 2 (cache), Task 3 (`research`, `research_state`, `categories_from`), dan `_client()`
  dari `web/printify.py`.
- Produces:
  - `catalog.provider_list(printify: PrintifyStore, client: Callable[[], PrintifyClient], blueprint_id: int, now) -> list[tuple[int, str]]`
  - `catalog.shipping_for(printify, client, blueprint_id, provider_id, now) -> ShippingInfo`

    Keduanya memakai cache dulu. Kalau cache kosong atau kedaluwarsa, mereka memanggil Printify dan
    menyimpan hasilnya. Error Printify diteruskan tanpa menyimpan apa pun.
  - `POST /api/catalog/research {category}`:
    - `200 {"added": [...]}`;
    - `409 {"error": "Already researched."}` kalau status bukan `available`;
    - `404 {"error": "Unknown category."}` untuk `other` atau slug/kata utama yang tidak dikenal.
  - `GET /api/catalog/shipping?blueprint_id=&provider_id=` (wajib `X-App-Token`):
    - `200 {"shipping_us_cents", "shipping_text", "handling_days"}`. `shipping_text` adalah `money(...)`
      atau `"No US shipping"`;
    - error Printify → `400 {"error": message}`; belum terhubung → `409`.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_web_catalog_api.py`, Printify palsu Tahap 4,
  `printify_app`):
  - `test_research_api`:
    - `{"category": "necklace"}` → 200, `added` berisi 3 seed, dan `keywords.txt` memuatnya;
    - panggilan kedua → 409 "Already researched.";
    - `{"category": "other"}` dan `{"category": "nope"}` → 404 "Unknown category.";
    - tanpa token aplikasi → 403.
  - `test_shipping_api_uses_cache`:
    - setelah sync, `GET /api/catalog/shipping?blueprint_id=384&provider_id=29` dengan `X-App-Token` →
      `{"shipping_us_cents": None, "shipping_text": "No US shipping", "handling_days": 4}`;
    - panggilan kedua tidak menambah request ke fake untuk path ongkir itu;
    - tanpa header → 403.
  - `test_providers_and_add_use_cache`:
    - `GET /api/printify/providers?blueprint_id=6` dua kali → hanya satu request providers ke fake;
    - `types/add` untuk (6, 99) setelah itu tidak meminta providers lagi.
  - `test_failures_are_not_cached`:
    - fake mengembalikan 500 untuk ongkir (4 kali) → `400` dengan pesan *Could not reach Printify…*;
    - fake normal kembali → panggilan berikutnya meminta lagi dan berhasil.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_catalog_api.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai Interfaces. `research` mengambil kategori dari `ENTRIES`, jadi
  tidak perlu katalog tersinkron, tetapi `other` dan kunci tak dikenal → 404.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_web_catalog_api.py tests/test_web_printify.py -q`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: catalog research and cached Printify details API"`

---

### Task 5: Halaman Catalog dan halaman kategori

**Files:**
- Modify: `etsy_insights/web/catalog.py` (halaman), `etsy_insights/web/templates/base.html` (menu),
  `etsy_insights/web/static/app.js`, `app.css`
- Create: `etsy_insights/web/templates/catalog.html`, `category.html`
- Test: `tests/test_web_catalog_pages.py`

**Interfaces:**
- Consumes: Task 3 (`summarize`, `sort_summaries`, `top_keywords`, `categories_from`), Task 4 (API).
- Produces:
  - `GET /catalog?q=&sort=&status=&mine=`
  - `GET /catalog/<slug>`
  - JS **Choose provider**:
    - mengambil `/api/printify/providers` (dengan `X-App-Token`) dan `/api/catalog/shipping`;
    - menampilkan *US shipping* dan *Production time: N days*;
    - **Add to my product types** memakai `/api/printify/types/add` lalu reload.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_web_catalog_pages.py`):
  - `test_catalog_without_sync`: berisi `"Connect Printify and run Sync to load the catalog."` dan
    tautan `/printify`. Menu berisi `href="/catalog"`.
  - `test_catalog_cards`: setelah `seed_ready_keyword(home)` dan
    `seed_printify(home, mug_cost=100, mug_shipping=0)`, halaman berisi:
    - `"Printify catalog"`, `"Sweatshirts"`, `"Mugs"`, `"N products"`;
    - `"Most searched:"`, `"Opportunities:"`, `"Ready to sell: 1"` (mug);
    - `"Uses up to 3 of your daily searches."`;
    - tombol *Research* (`data-api="/api/catalog/research"`);
    - `<img` dengan `loading="lazy"` dan `src="https://images.printify.com/sweat.png"`.

    Tanpa foto, kartu berisi `"No photo"`, dan halaman berisi `"Run Sync to load product photos."`.
  - `test_catalog_search_and_filters`:
    - `q=Necklace!` menemukan kategori necklace kalau blueprint-nya ada;
    - `status=not_researched` hanya berisi kategori tanpa keyword;
    - `mine=1` hanya kategori `in_my_products`;
    - `sort=name` berurutan abjad dengan *Other* terakhir.
  - `test_category_page`: `/catalog/mug` berisi:
    - kartu angka;
    - tabel *Top keywords* dengan tautan `/keyword/custom%20mug`;
    - `href="/opportunities?q=mug"`;
    - kisi produk dengan `"Choose provider"`, `"In my products"` untuk (68, 1), serta brand/model.
  - `test_unknown_category_page`: `/catalog/nope` → 404 berisi `"Unknown category."`.
  - `test_titles_are_escaped`: blueprint berjudul `"<script>alert(1)</script> Mug"` tampil ter-escape,
    tanpa tag `<script>alert`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_catalog_pages.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai spec §8. Kartu memakai kelas CSS yang ada (`panel`, `badge`,
  `btn`), ditambah kisi `.grid-cards` responsif. Status *Researched* ditampilkan sebagai tombol
  `disabled`, dan *In queue: N keywords* sebagai lencana.
- [ ] **Step 4: Jalankan dan lihat.**
  - Run: `.venv/bin/pytest -q`. Expected: semua PASS.
  - Ambil screenshot `/catalog` dan `/catalog/mug` dengan data uji di scratchpad, lalu periksa
    tata letaknya (kartu tidak terpotong, foto tidak meluber).
- [ ] **Step 5: Commit.** `git commit -m "feat: catalog and category pages"`

---

### Task 6: Smoke test, README, dan paket 5.0.0

**Files:**
- Create: `tests/test_catalog_smoke.py` (marker `smoke`, skip tanpa `CHROME_SMOKE_PATH`)
- Modify: `README.md`, `macos/README.txt`, `tests/printify_fake.py` (route gambar lokal)

- [ ] **Step 1: Tulis smoke test.**
  - Fake Printify juga melayani `/img/sweat.png` (PNG kecil), dan blueprint memakai `image_url` ke
    fake itu.
  - Karena aturan `https`, gunakan fake berbasis TLS (`FakePrintify(tls=...)`, sertifikat lokal seperti
    tes 4.0.1). `printify_app` mendapat parameter `ssl_context` yang diteruskan ke `PrintifyClient`.
    Chromium dijalankan dengan `ignore_https_errors=True` khusus untuk tes ini.
  - Alur: `/catalog` → klik **Research** di kartu Mugs → kartu menampilkan *In queue* → **View
    products** → **Choose provider** → pilih provider → ongkir tampil → isi biaya `4.80` → **Add to my
    product types** → `/printify` berisi model itu.
  - Pastikan tidak ada permintaan ke host selain `127.0.0.1`.
- [ ] **Step 2: Jalankan.** Run: `CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`. Expected: semua PASS (perbaiki yang perlu, ledger setiap penyimpangan).
- [ ] **Step 3: README.** Bagian baru **Catalog** (bahasa Indonesia):
  - cara menjelajah kategori dan arti status riset;
  - tombol Research dan kuota;
  - menambah model dari halaman kategori;
  - catatan bahwa foto dimuat dari server Printify.

  `macos/README.txt` mendapat satu baris ringkas.
- [ ] **Step 4: Semua tes + paket.** Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke && .venv/bin/python -m tools.build_app 5.0.0 && zipinfo dist/Etsy-Insights.zip | grep "MacOS/etsy-insights"`. Expected: semua PASS; `-rwxr-xr-x`.
- [ ] **Step 5: Commit dan salin.** `git commit -m "feat: catalog smoke test, README and 5.0.0 package"`, lalu `cp dist/Etsy-Insights.zip /home/user/`.
