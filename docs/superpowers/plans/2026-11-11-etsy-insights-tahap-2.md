# Etsy Insights — Tahap 2 (Panen + Sesi Harian) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bash mulai.command` menjalankan sesi harian yang aman. Setiap pencarian di Marketplace
Insights menyimpan data keyword utama dan memanen 130–180 keyword terkait. Excel menampilkan
peringkat peluang dengan level konversi Etsy.

**Architecture:** Tahap 2 menambah empat unit di atas fondasi Tahap 1:
- `parser.py` (fungsi murni: `RawResult` → `ParsedSearch`);
- `planner.py` (memilih keyword berikutnya menurut spec §16.3);
- `insights_page.py` (implementasi `InsightsPage` dengan Playwright, ditambah fungsi deteksi bahaya yang murni);
- perintah CLI `run`.

`store`, `score`, `export`, dan `session` disesuaikan untuk data panen. Tes yang menyentuh browser
memakai Chromium asli dengan semua URL Etsy dialihkan ke halaman/fixture palsu, jadi tidak ada
trafik ke Etsy.

**Tech Stack:** Python ≥ 3.11, `playwright` (sync API, `connect_over_cdp`), `openpyxl`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-11-etsy-insights-scraper-design.md`. **§16 (Revisi 1)
menggantikan bagian lain bila bertentangan.**

**Branch:** `tahap-2`, dibuat dari `tahap-1` (HEAD `cb63555`).

## Global Constraints

- Python ≥ 3.11. Dependensi runtime hanya `playwright>=1.48,<2` dan `openpyxl>=3.1,<4`. Dependensi dev: `pytest>=8`.
- macOS + Google Chrome. Playwright tidak pernah meluncurkan Chrome untuk sesi sungguhan; Chrome selalu disambung lewat `ensure_chrome` + `connected_browser`.
- **Tes tidak boleh menghubungi etsy.com atau situs eksternal mana pun.** Setiap tes browser memasang `context.route` untuk semua URL `https://www.etsy.com/**` (dan domain captcha), dan permintaan yang tidak dikenal dijawab 404.
- Semua teks yang dilihat pengguna dalam Bahasa Indonesia.
- Batas keras: `kuota_harian ≤ 30` (default 15). Batas lain sama dengan Tahap 1.
- Tidak ada proxy, penyamaran fingerprint, penembusan CAPTCHA, pemanggilan API internal Etsy secara langsung, atau tab paralel. Data hanya dibaca dari respons yang dimuat halaman itu sendiri.
- Fixture tes dibuat dari rekaman kenali yang sudah disensor. ID toko diganti `12345678`, dan kartu listing pesaing, data langganan, serta harga dibuang.
- Level konversi: 0 = Sangat rendah, 1 = Rendah, 2 = Biasa, 3 = Tinggi, 4 = Sangat tinggi.
- Test dijalankan dengan `.venv/bin/pytest -q`. Tes browser: `CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`.

## Review Focus

1. **Daftar keyword terkait "basi"** dari keyword sebelumnya (poll LLM yang asinkron) tiba saat pencarian berikutnya. Daftar itu tidak boleh dipakai untuk keyword baru. Dites di Task 4 `test_parse_sweatshirt_ignores_stale_poll` dan Task 7 `test_has_related_for_ignores_stale_poll`.
2. **Keyword salah ketik atau tanpa data** tetap memanen keyword terkaitnya dan tidak dihitung gagal. Dites di Task 6 `test_no_data_still_harvests`.
3. **Keyword yang sama muncul di banyak daftar terkait** tidak boleh menghasilkan duplikat, dan data hasil cari tidak boleh tertimpa data panen. Dites di Task 2 `test_save_harvest_updates_panen_row_without_duplicates` dan `test_save_harvest_skips_searched_keywords`.
4. **Jendela Terminal ditutup (SIGHUP/SIGTERM) atau Ctrl+C saat sesi berjalan:** baris sesi harus ditutup dan kunci sesi dilepas. Dites di Task 8 `test_sigterm_becomes_keyboard_interrupt` dan `test_lock_released_after_error`.
5. **Tampilan Etsy berubah** (kotak pencarian hilang): yang terjadi adalah kegagalan biasa, sesi berhenti setelah 3 kali dengan pesan kenali, dan tidak crash. Dites di Task 7 `test_search_box_missing_raises_page_load_timeout` (smoke) dan Task 6 tes `gagal_beruntun` yang sudah ada.

---

### Task 1: Model data baru + default config

**Files:**
- Modify: `etsy_insights/models.py`, `etsy_insights/config.py`, `config.toml`, `tests/test_config.py`, `tests/test_pacer.py`, `tests/test_session.py`, `tests/test_cli.py`

**Interfaces:**
- Produces (`models.py`):
  ```python
  CONVERSION_LEVEL_TEXT = {0: "Sangat rendah", 1: "Rendah", 2: "Biasa", 3: "Tinggi", 4: "Sangat tinggi"}
  # KeywordMetrics: tambah di akhir -> conversion_level: int | None = None ; wow_pct: float | None = None
  #   (conversion_rate kini berarti queryCvr Etsy, pecahan; hanya untuk hasil cari)
  @dataclass(frozen=True)
  class RelatedKeyword: keyword: str; search_volume: int | None; competition_value: float | None; conversion_level: int | None
  @dataclass(frozen=True)
  class EtsyQuota:
      total: int | None; remaining: int | None; low_threshold: int | None; reached: bool; search_allowed: bool
      @property
      def exhausted(self) -> bool   # reached or not search_allowed or (remaining is not None and low_threshold is not None and remaining <= low_threshold)
  @dataclass(frozen=True)
  class ParsedSearch: main: KeywordMetrics; related: tuple[RelatedKeyword, ...] = (); quota: EtsyQuota | None = None
  # ResultRow: tambah di akhir -> kind: str = "search"   ("search" | "panen")
  ```
- Produces (`config.py`): `Config.kuota_harian` default `15`, `HARD_LIMITS["kuota_harian"] = (None, 30)`, `Config.keyword_terkait_maks` default `200`.

- [ ] **Step 1: Ubah test yang terdampak menjadi gagal (RED)**
  - `tests/test_config.py::test_defaults_match_spec`: kuota diganti `(c.kuota_harian, c.durasi_sesi_menit) == (15, 45)`, terkait diganti `c.keyword_terkait_maks == 200`.
  - `test_hard_caps_clamp_with_warning`: harapan kuota diganti `30`.
  - Tambah test baru:
    ```python
    def test_etsy_quota_exhausted():
        from etsy_insights.models import EtsyQuota
        assert not EtsyQuota(15, 15, 5, False, True).exhausted
        assert EtsyQuota(15, 5, 5, False, True).exhausted
        assert EtsyQuota(15, 15, 5, True, True).exhausted and EtsyQuota(15, 15, 5, False, False).exhausted
        assert not EtsyQuota(None, None, None, False, True).exhausted
    ```
  - `tests/test_pacer.py::test_remaining_quota`: isinya diganti `remaining_quota(c, 10) == 5`, `remaining_quota(c, 20) == 0`, `remaining_quota(c, 0, max_keywords=3) == 3`, `remaining_quota(c, 14, max_keywords=3) == 1`.
  - `tests/test_session.py::test_quota_used_up_and_partially_used`: `range(48)` diganti `range(13)`.
  - `test_format_summary`: harapan diganti `"Sisa kuota hari ini: 12"`.
  - `tests/test_cli.py::test_cli_status`: harapan diganti `"Hari ini: 0/15 keyword dicek"`.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest -q`. Expected: FAIL pada test-test di atas (nilai lama 50/100/10, `EtsyQuota` belum ada).
- [ ] **Step 3: Implementasi** perubahan `models.py` dan `config.py` sesuai Interfaces. `config.toml`: `kuota_harian = 15` dengan komentar "Jumlah pencarian per hari. Setiap pencarian memanen ±130–180 keyword terkait. Batas keras: maks 30.", dan `keyword_terkait_maks = 200` dengan komentar "Maksimal keyword terkait yang disimpan per pencarian."
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: harvest data models, 15 searches/day default (hard cap 30)"
```

---

### Task 2: Store untuk data panen

**Files:**
- Modify: `etsy_insights/store.py`, `tests/helpers.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `RelatedKeyword`, `KeywordMetrics`, `ResultRow.kind` (Task 1).
- Produces (metode yang **ditambah**; metode lama `add_related`, `next_keyword`, dan `return_to_pending` tetap ada sampai Task 6):
  ```python
  def save_harvest(self, parent_id: int, related: Sequence[RelatedKeyword], max_count: int, max_depth: int, now: datetime) -> int  # jumlah keyword BARU
  def next_user_pending(self, exclude_ids: Collection[int] = ()) -> QueueItem | None   # status pending, added_at naik, id naik
  def harvest_candidates(self, max_depth: int, exclude_ids: Collection[int] = ()) -> list[ResultRow]  # hasil terbaru keyword berstatus 'harvested' dengan depth < max_depth
  def next_recheck(self, now: datetime, recheck_days: int, exclude_ids: Collection[int] = ()) -> QueueItem | None
  def return_to_queue(self, keyword_id: int) -> None        # 'pending' bila source user, selain itu 'harvested'
  def stop_reasons_on(self, day: date, tz: tzinfo) -> list[str]   # stop_reason sesi yang dimulai pada tanggal lokal itu
  ```
- Changes:
  - Skema `results` ditambah kolom `kind TEXT NOT NULL DEFAULT 'search'`, `conversion_level INTEGER`, dan `wow_pct REAL`.
  - Ada `_migrate()` yang menjalankan `ALTER TABLE results ADD COLUMN …` untuk kolom yang belum ada, supaya database lama di Mac pengguna tetap terbuka.
  - `save_result` menyimpan `kind='search'`, `conversion_level`, dan `wow_pct`.
  - `_result_row` mengisi `ResultRow.kind`, `metrics.conversion_level`, dan `metrics.wow_pct`.
  - `record_failure`: status `failed` kalau `fail_count ≥ 3`; selain itu kembali ke status antrean sesuai source (`pending` untuk user, `harvested` untuk related).
  - `recover_in_progress` memakai aturan status antrean yang sama.
- Aturan `save_harvest`:
  - Kalau `depth induk + 1 > max_depth`, kembalikan 0 tanpa menyimpan apa pun.
  - Keyword dinormalisasi, yang kosong dibuang, dan duplikat dalam satu daftar dibuang. Daftar dipotong menjadi `max_count` keyword pertama setelah langkah itu.
  - Keyword **baru**: insert `source='related'`, `parent_id`, `depth = depth induk + 1`, `status='harvested'`, ditambah satu baris `results` dengan `kind='panen'`. `has_data = search_volume is not None and search_volume > 0`. `conversion_rate` dan `raw_json` bernilai NULL. Dihitung sebagai keyword baru.
  - Keyword yang **sudah ada** dengan status `pending`, `harvested`, atau `failed`: baris `panen` miliknya diganti (DELETE baris panen lama untuk keyword itu, lalu INSERT). Status dan induknya tidak berubah, dan tidak dihitung baru.
  - Keyword dengan status lain (`done`, `no_data`, `in_progress`) dilewati.
- Produces (`tests/helpers.py`):
  - `make_related(keyword, volume=1000, comp=100, level=2) -> RelatedKeyword`.
  - `make_metrics` ditambah keyword arg `level=2` dan `wow=None` (diteruskan ke `conversion_level` / `wow_pct`).

- [ ] **Step 1: Tulis test yang gagal di `tests/test_store.py`**

```python
import sqlite3
from etsy_insights.store import Store
from tests.helpers import make_related

def test_save_result_keeps_level_and_wow():
    s = new_store("a")
    s.save_result(s.get("a").id, make_metrics(level=3, wow=22.7), make_raw("a"), T0, "t")
    [row] = s.latest_results()
    assert (row.kind, row.metrics.conversion_level, row.metrics.wow_pct) == ("search", 3, 22.7)

def test_save_harvest_inserts_new_and_counts():
    s = new_store("a")
    n = s.save_harvest(s.get("a").id, [make_related("x"), make_related("y", level=4), make_related("A"), make_related(" ")], 200, 2, T0)
    assert n == 2
    x = s.get("x")
    assert (x.status, x.depth, x.parent_keyword, x.source) == ("harvested", 1, "a", "related")
    rows = {r.keyword: r for r in s.latest_results()}
    assert rows["y"].kind == "panen" and rows["y"].metrics.conversion_level == 4 and rows["y"].metrics.conversion_rate is None

def test_save_harvest_max_count_and_depth():
    s = new_store("a")
    assert s.save_harvest(s.get("a").id, [make_related("x"), make_related("y")], 1, 2, T0) == 1 and s.get("y") is None
    s.save_harvest(s.get("x").id, [make_related("x2")], 200, 2, T0)
    assert s.get("x2").depth == 2
    assert s.save_harvest(s.get("x2").id, [make_related("x3")], 200, 2, T0) == 0 and s.get("x3") is None

def test_save_harvest_updates_panen_row_without_duplicates():
    s = new_store("a", "b")
    s.save_harvest(s.get("a").id, [make_related("x", volume=1000)], 200, 2, T0)
    assert s.save_harvest(s.get("b").id, [make_related("x", volume=2000)], 200, 2, T0 + timedelta(hours=1)) == 0
    assert [r.metrics.search_volume for r in s.all_results() if r.keyword == "x"] == [2000]
    assert s.get("x").parent_keyword == "a"

def test_save_harvest_skips_searched_keywords():
    s = new_store("a", "b")
    s.save_result(s.get("a").id, make_metrics(volume=1000), make_raw("a"), T0, "t")
    s.save_harvest(s.get("b").id, [make_related("a", volume=5)], 200, 2, T0 + timedelta(hours=1))
    [row] = [r for r in s.latest_results() if r.keyword == "a"]
    assert (row.kind, row.metrics.search_volume) == ("search", 1000)

def test_queue_primitives():
    s = new_store("u1", "u2")
    s.save_harvest(s.get("u1").id, [make_related("h1"), make_related("h2")], 200, 2, T0)
    s.save_harvest(s.get("h1").id, [make_related("deep")], 200, 2, T0)
    assert s.next_user_pending().keyword == "u1"
    assert s.next_user_pending(exclude_ids={s.get("u1").id}).keyword == "u2"
    assert sorted(r.keyword for r in s.harvest_candidates(2)) == ["h1", "h2"]
    assert [r.keyword for r in s.harvest_candidates(2, exclude_ids={s.get("h1").id})] == ["h2"]
    s.save_result(s.get("u1").id, make_metrics(), make_raw("u1"), T0 - timedelta(days=31), "t")
    s.save_result(s.get("u2").id, make_metrics(), make_raw("u2"), T0 - timedelta(days=3), "t")
    assert s.next_recheck(T0, 30).keyword == "u1" and s.next_recheck(T0, 30, exclude_ids={s.get("u1").id}) is None

def test_failure_and_recovery_return_to_source_queue():
    s = new_store("a")
    s.save_harvest(s.get("a").id, [make_related("x")], 200, 2, T0)
    x = s.get("x").id
    s.mark_in_progress(x)
    assert s.record_failure(x) == "harvested"
    s.mark_in_progress(x); s.recover_in_progress()
    assert s.get("x").status == "harvested"
    s.mark_in_progress(s.get("a").id); s.return_to_queue(s.get("a").id)
    assert s.get("a").status == "pending"

def test_stop_reasons_on():
    s = Store(":memory:")
    sid = s.start_session(T0); s.end_session(sid, T0, "kuota_etsy", None)
    assert s.stop_reasons_on(T0.date(), T0.tzinfo) == ["kuota_etsy"]
    assert s.stop_reasons_on((T0 + timedelta(days=1)).date(), T0.tzinfo) == []

def test_migrates_old_database(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE keywords (id INTEGER PRIMARY KEY, keyword TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
            parent_id INTEGER, depth INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', added_at TEXT NOT NULL,
            last_checked_at TEXT, fail_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE results (id INTEGER PRIMARY KEY, keyword_id INTEGER NOT NULL, checked_at TEXT NOT NULL,
            has_data INTEGER NOT NULL, search_volume INTEGER, conversion_rate REAL, competition_value REAL,
            competition_kind TEXT, trend_json TEXT, related_json TEXT, raw_json TEXT, parser_version TEXT);""")
    con.close()
    s = Store(db); s.sync_user_keywords(["a"], T0)
    s.save_result(s.get("a").id, make_metrics(level=1), make_raw("a"), T0, "t")
    assert s.latest_results()[0].metrics.conversion_level == 1
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_store.py -q`. Expected: FAIL (`make_related`/`save_harvest` belum ada).
- [ ] **Step 3: Implementasi** di `store.py` dan `tests/helpers.py` sesuai Interfaces dan aturan di atas.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS (tes Tahap 1 untuk `add_related`/`next_keyword` tetap lulus).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: store harvested keywords, queue primitives and schema migration"
```

---

### Task 3: Skor memakai level konversi + planner

**Files:**
- Create: `etsy_insights/planner.py`, `tests/test_planner.py`
- Modify: `etsy_insights/score.py`, `tests/helpers.py`, `tests/test_score.py`

**Interfaces:**
- Consumes: `Store.next_user_pending`, `harvest_candidates`, `next_recheck`, `get`, `pending_queue`, `latest_results` (Task 2). `score_all` (Tahap 1).
- Produces:
  - `score.py`: metrik "conversion" dibaca dari `metrics.conversion_level` (bukan `conversion_rate`).
  - `planner.py`:
    ```python
    def select_next(store: Store, cfg: Config, now: datetime, exclude_ids: Collection[int] = ()) -> QueueItem | None
    def upcoming(store: Store, cfg: Config, limit: int = 50) -> list[QueueItem]
    ```
    - `select_next` mengembalikan yang pertama dari daftar ini:
      1. `next_user_pending(exclude)`;
      2. kandidat `harvest_candidates(cfg.kedalaman_maks, exclude)` yang **layak** dan skornya tertinggi, dengan skor dihitung `score_all(store.latest_results(), cfg)` atas seluruh data;
      3. `next_recheck(now, cfg.cek_ulang_setelah_hari, exclude)`.

      Kandidat yang tidak layak (label "Data kurang") tidak pernah dipilih.
    - `upcoming` menghasilkan `pending_queue()` diikuti kandidat panen yang layak menurut urutan skor, dipotong `limit`.
  - `tests/helpers.py`:
    - `make_row(keyword, volume, level, comp, kind="count", source="user", parent=None, has_data=True, trend=(), keyword_id=0, wow=None, rate=None, row_kind="search")`.
    - Argumen ke-3 kini `conversion_level`. `rate` mengisi `conversion_rate`, `wow` mengisi `wow_pct`, `row_kind` mengisi `ResultRow.kind`.
    - Status bernilai `"harvested"` kalau `row_kind == "panen"`, selain itu `"done"`/`"no_data"`.

- [ ] **Step 1: Tulis test yang gagal**
  - `tests/test_score.py`: ganti argumen ke-3 setiap `make_row` dengan level bilangan bulat yang urutannya sama:
    - `test_score_example_from_spec`: `a`=3, `b`=2, `c`=1, `d`=4.
    - `test_emas_when_top_third_everywhere`: `a`=3, `b`=2, `c`=1, `e`=4.
    - `test_competition_levels`: semua 2.

    Semua harapan skor dan label tetap sama. Tambah satu test:
    ```python
    def test_conversion_uses_level_not_rate():
        rows = [make_row("hi", 1000, 4, 100, rate=0.0001), make_row("lo", 1000, 0, 100, rate=0.9)]
        by = {s.row.keyword: s for s in score_all(rows, Config())}
        assert by["hi"].p_conversion == 100 and by["lo"].p_conversion == 0
    ```
  - `tests/test_planner.py`:
    ```python
    from datetime import timedelta
    from etsy_insights.config import Config
    from etsy_insights.planner import select_next, upcoming
    from etsy_insights.store import Store
    from tests.helpers import T0, make_metrics, make_raw, make_related

    def searched_store():
        s = Store(":memory:"); s.sync_user_keywords(["a"], T0)
        s.save_result(s.get("a").id, make_metrics(volume=1000, level=2, comp=100), make_raw("a"), T0, "t")
        s.save_harvest(s.get("a").id, [make_related("x", 5000, 50, 4), make_related("y", 200, 900000, 0),
                                       make_related("z", 50, 10, 4)], 200, 2, T0)
        return s

    def test_select_next_prefers_user_pending():
        s = searched_store(); s.sync_user_keywords(["b"], T0)
        assert select_next(s, Config(), T0).keyword == "b"

    def test_select_next_picks_best_eligible_harvested():
        s = searched_store()
        assert select_next(s, Config(), T0).keyword == "x"
        assert select_next(s, Config(), T0, {s.get("x").id}).keyword == "y"
        assert select_next(s, Config(), T0, {s.get("x").id, s.get("y").id}) is None   # z tidak layak (volume < 100)

    def test_select_next_falls_back_to_recheck():
        s = Store(":memory:"); s.sync_user_keywords(["a"], T0)
        s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0 - timedelta(days=31), "t")
        assert select_next(s, Config(), T0).keyword == "a"

    def test_upcoming_lists_user_then_ranked_harvested():
        s = searched_store(); s.sync_user_keywords(["b", "c"], T0)
        assert [q.keyword for q in upcoming(s, Config())] == ["b", "c", "x", "y"]
        assert [q.keyword for q in upcoming(s, Config(), limit=3)] == ["b", "c", "x"]
    ```
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_score.py tests/test_planner.py -q`. Expected: FAIL (`planner` belum ada, dan `p_conversion` masih memakai rate).
- [ ] **Step 3: Implementasi** perubahan `score.py`, `planner.py` baru, dan `make_row` baru.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: score by Etsy conversion level; planner picks best harvested keyword"
```

---

### Task 4: Parser + fixture dari rekaman

**Files:**
- Create: `etsy_insights/parser.py`, `tests/fixtures/personalized.json`, `tests/fixtures/swearshirt.json`, `tests/fixtures/sweatshirt.json`, `tests/fixtures/custom.json`, `tests/test_parser.py`

**Interfaces:**
- Consumes: `RawResult`, `CapturedResponse`, `KeywordMetrics`, `RelatedKeyword`, `EtsyQuota`, `ParsedSearch`, `ParseError` (Task 1); `normalize_keyword` (store).
- Produces:
  ```python
  PARSER_VERSION = "1"
  RESULTS_PATH = "/marketplace-insights/results-data"
  POLL_PATH = "/llm-exploratory-keywords/search/poll"
  ENQUEUE_PATH = "/llm-exploratory-keywords/search/enqueue"
  def is_results_for(resp: CapturedResponse, keyword: str) -> bool   # path berakhiran RESULTS_PATH, status 200, body dict berisi "stats", query ternormalisasi == keyword ternormalisasi
  def related_rows_for(responses: Sequence[CapturedResponse], keyword: str) -> list[dict] | None
  def parse_search(raw: RawResult) -> ParsedSearch
  ```
- Aturan:
  - `related_rows_for` mencari dari belakang:
    1. respons POLL dengan `status == "success"` dan `inputKeyword` yang cocok;
    2. kalau tidak ada, respons ENQUEUE terakhir yang punya `cachedData.results`;
    3. kalau tidak ada juga, `None`.

    Poll yang `inputKeyword`-nya beda **tidak pernah** dipakai.
  - `parse_search`:
    - Ambil respons `is_results_for` **terakhir**. Kalau tidak ada, `ParseError(f"Data utama untuk '{raw.keyword}' tidak ditemukan.")`.
    - Dari `stats`: `searchVolume` → `search_volume`, `avgTotalListings` → `competition_value`, `cvr` → `conversion_level`, `queryCvr` → `conversion_rate`.
    - `has_data = bool(searchVolume)`. `competition_kind = "count"` kalau `avgTotalListings` bukan None.
    - `trend` = `searchVolume` dari `dailyStats.stats`. `wow_pct = wowData.value`.
    - `main.related` = tuple nama keyword terkait.
    - `quota` = `EtsyQuota(quotaData.totalQuota, quotaData.remainingQuota, quotaData.lowRemainingQuotaThreshold, bool(isQuotaReached), isSearchAllowed is not False)`, atau `None` kalau `quotaData` dan kedua flag itu tidak ada.
    - Baris terkait tanpa `searchTerm` string dilewati. Nilai bukan angka menjadi None.

- [ ] **Step 1: Buat fixture dari rekaman yang sudah disensor**

Jalankan script sekali pakai ini (tidak di-commit) dengan `python3 -I`. Argumennya adalah rekaman di scratchpad (`kenali-in/kenali-20261111-0945.json`) dan folder `tests/fixtures`. Script hanya menyimpan respons berindeks berikut, persis dalam urutan rekaman:
- `personalized` = `[10, 14, 15, 16]`
- `swearshirt` = `[18, 19, 20, 21, 22, 23]`
- `sweatshirt` = `[23, 24, 25, 26]` (poll basi #23 sengaja disertakan)
- `custom` = `[28, 29, 30, 31, 32, 33, 34, 35, 36]`

Format setiap file: `{"keyword": <kw>, "page_url": "https://www.etsy.com/your/shops/me/marketplace-insights/search?query=<kw>&search_trigger=results_search_bar", "responses": [{"url", "status", "body"}]}`.

Pembersihan:
- `68976357` diganti `12345678` di URL.
- Body `results-data` hanya menyimpan kunci `searchTermId, isSearchAllowed, isQuotaReached, quotaData, stats, dailyStats, wowData, similarSearchTerms, competitiveResearchListingCards`, ditambah `competitivePriceData` yang hanya berisi `searchTermMedianPrice` (`listingPriceRange` berisi harga toko Anda sendiri, jadi dibuang).
- Body `nav-badge-counts` (#10) diganti `{"counts": {"orders": 0}}` sebagai respons pengganggu.

Lalu pastikan:

Run: `grep -c "68976357\|eyJ" tests/fixtures/*.json`
Expected: semua `0`. (Tanda `@` bisa muncul di judul listing pesaing, jadi tidak dicek.)

- [ ] **Step 2: Tulis test yang gagal di `tests/test_parser.py`**

```python
import dataclasses, json
from pathlib import Path
import pytest
from etsy_insights.models import CapturedResponse, EtsyQuota, ParseError, RawResult, RelatedKeyword
from etsy_insights.parser import parse_search, related_rows_for

FIX = Path(__file__).parent / "fixtures"

def load_raw(name, keyword=None):
    d = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    return RawResult(keyword or d["keyword"], d["page_url"],
                     tuple(CapturedResponse(r["url"], r["status"], r["body"]) for r in d["responses"]), "")

def test_parse_sweatshirt_main_metrics():
    p = parse_search(load_raw("sweatshirt"))
    m = p.main
    assert (m.has_data, m.search_volume, m.competition_value, m.competition_kind, m.conversion_level) == (True, 46395, 1863632, "count", 0)
    assert m.conversion_rate == pytest.approx(0.00014224041690609525) and m.wow_pct == 22.7
    assert len(m.trend) == 30 and (m.trend[0], m.trend[-1]) == (1194, 1949)
    assert p.quota == EtsyQuota(15, 15, 5, False, True) and not p.quota.exhausted

def test_parse_sweatshirt_ignores_stale_poll():
    p = parse_search(load_raw("sweatshirt"))
    assert len(p.related) == 180 and p.related[1].keyword == "gift for him"   # dari enqueue, bukan poll 'swearshirt'

def test_parse_personalized_uses_cached_enqueue():
    p = parse_search(load_raw("personalized"))
    assert p.main.search_volume == 67930 and len(p.related) == 130
    assert p.related[0] == RelatedKeyword("personalized gifts", 113851, 1816694, 1)

def test_parse_custom_uses_matching_poll():
    p = parse_search(load_raw("custom"))
    assert len(p.related) == 180 and p.related[0] == RelatedKeyword("personalized gift", 257361, 712366, 0)
    assert p.main.related[0] == "personalized gift"

def test_parse_typo_has_no_data_but_related():
    p = parse_search(load_raw("swearshirt"))
    assert (p.main.has_data, p.main.search_volume, p.main.conversion_level) == (False, 0, None)
    assert [r.keyword for r in p.related[:2]] == ["gift for her", "craft supplies"]

def test_quota_exhausted_variants():
    raw = load_raw("sweatshirt")
    def with_body(change):
        responses = []
        for r in raw.responses:
            body = r.body
            if isinstance(body, dict) and "stats" in body:
                body = json.loads(json.dumps(body)); change(body)
            responses.append(CapturedResponse(r.url, r.status, body))
        return dataclasses.replace(raw, responses=tuple(responses))
    assert parse_search(with_body(lambda b: b["quotaData"].update(remainingQuota=5))).quota.exhausted
    assert parse_search(with_body(lambda b: b.update(isSearchAllowed=False))).quota.exhausted

def test_missing_or_other_keyword_raises_parse_error():
    with pytest.raises(ParseError):
        parse_search(load_raw("sweatshirt", keyword="hoodie"))
    raw = load_raw("custom")
    with pytest.raises(ParseError):
        parse_search(dataclasses.replace(raw, responses=tuple(r for r in raw.responses if "results-data" not in r.url)))

def test_related_rows_none_without_lists():
    assert related_rows_for((), "x") is None
```

- [ ] **Step 3: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_parser.py -q`. Expected: FAIL (`etsy_insights.parser` belum ada).
- [ ] **Step 4: Implementasi `etsy_insights/parser.py`** sesuai aturan di atas.
- [ ] **Step 5: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: parse Marketplace Insights responses into main + harvested keywords"
```

---

### Task 5: Excel untuk data panen

**Files:**
- Modify: `etsy_insights/export.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `CONVERSION_LEVEL_TEXT` (Task 1), `ResultRow.kind`, `planner.upcoming` (Task 3, hanya di test).
- Produces:
  ```python
  PELUANG_HEADERS = ["Keyword", "Volume pencarian", "Pesaing (listing)", "Konversi", "Rasio konversi",
                     "Pencarian per listing", "Skor", "Label", "Tren mingguan", "Asal keyword", "Tanggal data"]
  SEMUA_HEADERS = ["Keyword", "Jenis data", "Status", "Tanggal data", "Volume pencarian", "Pesaing (listing)",
                   "Konversi", "Rasio konversi", "Tren mingguan", "Label terbaru"]
  ANTREAN_HEADERS = ["Urutan", "Keyword", "Sumber", "Kedalaman", "Asal keyword"]
  STATUS_TEXT = {"pending": "menunggu", "in_progress": "sedang dicek", "done": "sudah dicari",
                 "no_data": "tanpa data", "failed": "gagal", "harvested": "hasil panen"}
  # export_excel(...) — signature tidak berubah
  ```
- Aturan:
  - Kolom **Konversi** = `CONVERSION_LEVEL_TEXT[level]` atau `""`.
  - Kolom **Rasio konversi** = `conversion_rate` dengan format `0.000%`.
  - Kolom **Tren mingguan** = `f"{wow:+.1f}%"` atau `""`.
  - Kolom **Asal keyword**:
    - `source == "user"` → `"daftar Anda"`;
    - `kind == "panen"` → `f"panen dari: {parent}"`;
    - selain itu → `f"dicari (asal: {parent})"`.
  - Kolom **Jenis data** = `"panen"` atau `"dicari"`. Kolom **Status** = `STATUS_TEXT`.
  - Sheet **Antrean**: kolom Urutan dimulai dari 1; Sumber berisi `"daftar Anda"` atau `"hasil panen"`; Asal berisi induk atau `""`.
  - **Teks aman**: untuk setiap sel string, karakter ilegal dibuang (`openpyxl.cell.cell.ILLEGAL_CHARACTERS_RE`). Kalau string diawali `=`, `+`, `-`, atau `@`, set `cell.data_type = "s"`.
  - Baris info, header, freeze `A3`, autofilter, dan warna label tetap seperti Tahap 1 (kolom Label sekarang kolom ke-8).

- [ ] **Step 1: Ganti isi `tests/test_export.py` dengan test berikut (RED)**

```python
import pytest
from openpyxl import load_workbook
from etsy_insights.config import Config
from etsy_insights.export import ANTREAN_HEADERS, PELUANG_HEADERS, SEMUA_HEADERS, export_excel
from etsy_insights.planner import upcoming
from etsy_insights.score import score_all
from etsy_insights.store import Store
from tests.helpers import T0, make_metrics, make_raw, make_related, make_row

ROWS = [make_row("a", 1000, 3, 100, wow=12.0, rate=0.00022), make_row("b", 500, 2, 1000),
        make_row("c", 2000, 1, 5000, source="related", parent="a", row_kind="panen"),
        make_row("e", 4000, 4, 10), make_row("d", 50, 4, 1)]

def test_export_peluang_sheet(tmp_path):
    path = export_excel(score_all(ROWS, Config()), ROWS, [], tmp_path, T0.date())
    ws = load_workbook(path)["Peluang"]
    assert [c.value for c in ws[2]] == PELUANG_HEADERS and ws.freeze_panes == "A3"
    assert [ws.cell(r, 1).value for r in range(3, 7)] == ["e", "a", "c", "b"]
    row_a = [c.value for c in ws[4]]
    assert row_a[3] == "Tinggi" and row_a[4] == pytest.approx(0.00022) and row_a[8] == "+12.0%" and row_a[9] == "daftar Anda"
    assert ws.cell(4, 5).number_format == "0.000%" and ws.cell(5, 10).value == "panen dari: a"
    assert ws.cell(3, 8).value == "Emas" and ws.cell(3, 8).fill.fgColor.rgb.endswith("FFD966")

def test_export_semua_data_indonesian_status(tmp_path):
    ws = load_workbook(export_excel(score_all(ROWS, Config()), ROWS, [], tmp_path, T0.date()))["Semua data"]
    assert [c.value for c in ws[2]] == SEMUA_HEADERS
    by_kw = {ws.cell(r, 1).value: [c.value for c in ws[r]] for r in range(3, ws.max_row + 1)}
    assert by_kw["c"][1:3] == ["panen", "hasil panen"] and by_kw["a"][1:3] == ["dicari", "sudah dicari"]

def test_export_text_is_safe(tmp_path):
    rows = [make_row("=sum(", 1000, 2, 10), make_row("bad\x01kw", 900, 2, 10)]
    ws = load_workbook(export_excel(score_all(rows, Config()), rows, [], tmp_path, T0.date()))["Peluang"]
    cells = {ws.cell(r, 1).value: ws.cell(r, 1) for r in range(3, ws.max_row + 1)}
    assert cells["=sum("].data_type == "s" and "badkw" in cells

def test_export_empty(tmp_path):
    wb = load_workbook(export_excel([], [], [], tmp_path, T0.date()))
    assert "0 keyword layak" in wb["Peluang"]["A1"].value
    assert [c.value for c in wb["Peluang"][2]] == PELUANG_HEADERS
    assert [c.value for c in wb["Antrean"][2]] == ANTREAN_HEADERS

def test_export_queue_sheet(tmp_path):
    s = Store(":memory:"); s.sync_user_keywords(["a", "b"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    s.save_harvest(s.get("a").id, [make_related("x", 5000, 50, 4)], 200, 2, T0)
    ws = load_workbook(export_excel([], [], upcoming(s, Config()), tmp_path, T0.date()))["Antrean"]
    assert [c.value for c in ws[3]] == [1, "b", "daftar Anda", 0, None]
    assert [c.value for c in ws[4]] == [2, "x", "hasil panen", 1, "a"]
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_export.py -q`. Expected: FAIL (header lama).
- [ ] **Step 3: Implementasi** perubahan `export.py` sesuai aturan di atas. (Asal kosong ditulis `""`; openpyxl membacanya kembali sebagai `None`.)
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Excel shows conversion level, harvest origin and safe text"
```

---

### Task 6: Sesi memakai panen, planner, dan kuota Etsy

**Files:**
- Modify: `etsy_insights/session.py`, `etsy_insights/store.py` (hapus `add_related`, `next_keyword`, `return_to_pending`), `tests/helpers.py`, `tests/test_session.py`, `tests/test_store.py` (hapus tes metode yang dihapus)

**Interfaces:**
- Consumes: `planner.select_next`, `planner.upcoming` (Task 3), `Store.save_harvest`, `return_to_queue`, `stop_reasons_on`, `last_session` (Task 2), `ParsedSearch`/`EtsyQuota` (Task 1).
- Produces:
  - `SessionDeps.parse: Callable[[RawResult], ParsedSearch]`.
  - `StopReason` ditambah:
    - `ETSY_QUOTA = "kuota_etsy"`, dengan `REASON_TEXT` "Etsy menandai kuota Marketplace Insights hampir/sudah habis. Coba lagi besok.";
    - `PAGE_UNAVAILABLE = "halaman_tidak_terbuka"`, dengan `REASON_TEXT` "Halaman Etsy tidak bisa dibuka (internet lambat?). Coba lagi nanti.".
  - `SessionSummary.new_keywords` = jumlah keyword baru hasil panen. `queue_left = len(upcoming(store, cfg, limit=10**9))`.
- Perubahan algoritma (sisanya sama dengan Tahap 1):
  - **Pra-cek:**
    - setelah pengecekan cooldown: kalau `"kuota_etsy" in store.stop_reasons_on(hari ini)` → kembalikan `ETSY_QUOTA` tanpa membuat baris sesi (tidak bisa dilewati dengan `ignore_cooldown`);
    - simpan `prev = store.last_session()` **sebelum** `start_session`.
  - **`page.open()`:** `PageLoadTimeout` → stop `PAGE_UNAVAILABLE`; `BrowserClosed` → stop `BROWSER_CLOSED`.
  - **Pemilihan keyword:** `item = select_next(store, cfg, clock(), tried)`.
  - **Jeda antar-sesi**, sebelum pencarian pertama (`checked == 0`) dan kalau `prev` ada: `wait = pacer.gap_seconds() - (clock() - (prev["ended_at"] or prev["started_at"])).total_seconds()`. Kalau `wait > 0`, panggil `sleep(wait)`, lalu cek durasi lagi.
  - **Setiap `page.check_danger()`** di dalam loop (setelah search maupun setelah `PageLoadTimeout`) dibungkus: `BrowserClosed` → `return_to_queue`, lalu stop `BROWSER_CLOSED`.
  - **Semua `return_to_pending`** diganti `return_to_queue`.
  - **Setelah parse berhasil:**
    1. `save_result(parsed.main)`;
    2. `succeeded`/`no_data` dihitung dari `main.has_data`;
    3. `new_keywords += store.save_harvest(item.id, parsed.related, cfg.keyword_terkait_maks, cfg.kedalaman_maks, clock())`, selalu, juga untuk `no_data`;
    4. kalau `parsed.quota and parsed.quota.exhausted` → stop `ETSY_QUOTA` (tanpa cooldown, tanpa dwell);
    5. selain itu `dwell`.
- `tests/helpers.py`:
  - `FakePage.related` berisi `dict[str, tuple[tuple[str, int, int, int], ...]]` (keyword, volume, pesaing, level).
  - Outcome baru: `"quota"` (body ditandai, parse menghasilkan kuota habis) dan `"closed_on_check"` (search normal, lalu `check_danger()` melempar `BrowserClosed`).
  - `fake_parse` mengembalikan `ParsedSearch(main=…, related=tuple(RelatedKeyword(*t) for t in body["related"]), quota=EtsyQuota(15, 5 if outcome == "quota" else 15, 5, False, True))`. Untuk `"no_data"`, `main=KeywordMetrics(has_data=False)`.

- [ ] **Step 1: Ubah test (RED)**
  - Di `tests/test_session.py`, ganti `test_related_keywords_follow_user_keywords` dengan tes-tes di bawah ini.
  - Hapus tes `add_related`/`next_keyword` lama di `tests/test_store.py`: `test_sync_promotes_related_to_user` (ganti dengan versi `save_harvest` di bawah), `test_queue_order_user_first_then_by_depth`, `test_add_related_respects_max_count_and_depth`, `test_add_related_skips_self_existing_blank`, `test_next_keyword_excludes_ids`, `test_recheck_only_when_no_pending_and_old_enough`.
  - Di `test_three_failures_mark_failed`, ganti `next_keyword(T0, 30)` dengan `next_user_pending()`.
  - Di `test_latest_results_newest_per_keyword_with_parent`, ganti `add_related(...)` dengan `save_harvest(..., [make_related("b")], 200, 2, T0)`, dan ganti harapan `len(s.all_results()) == 2` dengan `== 3` (dua hasil cari + satu baris panen).

```python
# tests/test_session.py
import pytest
from etsy_insights.models import PageLoadTimeout

def test_harvest_then_best_harvested_is_searched():
    clock, store, page = setup("a", related={"a": (("x", 5000, 50, 4), ("y", 200, 900000, 0))})
    s = run_session(make_deps(store, page, clock), max_keywords=2)
    assert page.searched == ["a", "x"] and s.new_keywords == 2
    assert (store.get("x").status, store.get("y").status, store.get("x").depth) == ("done", "harvested", 1)

def test_harvest_respects_depth():
    clock, store, page = setup("a", related={"a": (("x", 5000, 50, 4),), "x": (("z", 9000, 5, 4),)})
    s = run_session(make_deps(store, page, clock), max_keywords=5)
    assert page.searched == ["a", "x"] and store.get("z").depth == 2 and s.stop_reason is StopReason.QUEUE_EMPTY

def test_no_data_still_harvests():
    clock, store, page = setup("a", outcomes={"a": "no_data"}, related={"a": (("x", 5000, 50, 4),)})
    s = run_session(make_deps(store, page, clock), max_keywords=1)
    assert (s.no_data, s.failed, store.get("x").status) == (1, 0, "harvested")

def test_etsy_quota_stops_and_blocks_rest_of_day():
    clock, store, page = setup("a", "b", outcomes={"a": "quota"})
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, s.cooldown_until, store.get("a").status) == (StopReason.ETSY_QUOTA, 1, None, "done")
    page2 = FakePage(clock)
    assert run_session(make_deps(store, page2, clock)).stop_reason is StopReason.ETSY_QUOTA and page2.opened == 0
    clock.advance(86400)
    assert run_session(make_deps(store, FakePage(clock), clock)).stop_reason is not StopReason.ETSY_QUOTA

def test_inter_session_gap():
    clock, store, page = setup("a")
    sid = store.start_session(T0 - timedelta(seconds=60))
    store.end_session(sid, T0 - timedelta(seconds=5), "antrean_kosong", None)
    run_session(make_deps(store, page, clock, Config(jeda_antar_keyword_detik=(20, 20))))
    assert clock.sleeps == [pytest.approx(15)]

def test_browser_closed_during_danger_check():
    clock, store, page = setup("a", outcomes={"a": "closed_on_check"})
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.BROWSER_CLOSED and (store.get("a").status, store.get("a").fail_count) == ("pending", 0)

def test_open_timeout_stops_cleanly():
    clock, store, page = setup("a", open_error=PageLoadTimeout("dashboard"))
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.PAGE_UNAVAILABLE and store.last_session()["stop_reason"] == "halaman_tidak_terbuka"

def test_failed_harvested_keyword_returns_to_harvested():
    clock, store, page = setup("a", outcomes={"x": "parse_error"}, related={"a": (("x", 5000, 50, 4),)})
    run_session(make_deps(store, page, clock), max_keywords=2)
    assert (store.get("x").status, store.get("x").fail_count) == ("harvested", 1)

# tests/test_store.py (pengganti)
def test_sync_promotes_harvested_to_user():
    s = new_store("a"); s.save_harvest(s.get("a").id, [make_related("b")], 200, 2, T0)
    assert s.sync_user_keywords(["b"], T0) == 1
    b = s.get("b"); assert (b.source, b.depth, b.parent_keyword) == ("user", 0, None)
```

> Catatan: `sync_user_keywords` untuk keyword `harvested` mengubah `source` menjadi `user` dan `status` menjadi `pending`, supaya keyword itu masuk antrean pengguna. Perubahan status ini ditambahkan di task ini.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_session.py tests/test_store.py -q`. Expected: FAIL (`ParsedSearch` belum dipakai sesi, dan `StopReason.ETSY_QUOTA` belum ada).
- [ ] **Step 3: Implementasi** perubahan `session.py`, `store.py` (hapus metode lama; `sync_user_keywords` mengubah status `harvested` → `pending` saat dipromosikan), dan `tests/helpers.py`.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: session harvests related keywords, follows planner, stops on Etsy quota"
```

---

### Task 7: Halaman Insights asli (Playwright) + deteksi bahaya

**Files:**
- Create: `etsy_insights/insights_page.py`, `tests/test_insights_page.py`, `tests/test_insights_page_smoke.py`

**Interfaces:**
- Consumes: `Pacer` (Tahap 1); `is_results_for`, `related_rows_for` (Task 4); `models` (`RawResult`, `CapturedResponse`, `DangerSignal`, `NotLoggedIn`, `PageLoadTimeout`, `BrowserClosed`).
- Produces:
  ```python
  DASHBOARD_URL = "https://www.etsy.com/your/shops/me/dashboard"
  INSIGHTS_URL = "https://www.etsy.com/your/shops/me/marketplace-insights"
  NAV_SELECTOR = 'a[data-app-key="marketplace-insights"]'
  SEARCH_INPUT_SELECTORS = ('input[aria-label="Input to search for keywords"]', 'input[placeholder*="keyword" i]',
                            'main input[type="search"]', 'main input[type="text"]')
  CAPTCHA_MARKERS = ("captcha", "datadome", "challenges.cloudflare.com", "hcaptcha", "recaptcha")
  VERIFY_TEXTS = ("verify you are a human", "verify you're a human", "unusual activity", "are you a robot", "press & hold")
  def detect_danger(url: str, frame_urls: Sequence[str], body_text: str, http_statuses: Sequence[int]) -> DangerSignal | None
  def has_results_for(captured: Sequence[CapturedResponse], keyword: str) -> bool
  def has_related_for(captured: Sequence[CapturedResponse], keyword: str) -> bool
  class EtsyInsightsPage:   # memenuhi protokol InsightsPage
      def __init__(self, context, pacer: Pacer, rng: random.Random, *, dashboard_url: str = DASHBOARD_URL,
                   settle_seconds: tuple[float, float] = (3, 8), input_timeout: float = 10,
                   results_timeout: float = 30, related_timeout: float = 20, log: Callable[[str], None] = lambda m: None)
      def open(self) -> None
      def search(self, keyword: str) -> RawResult
      def check_danger(self) -> DangerSignal | None
      def dwell(self, seconds: float, scroll: bool) -> None
  ```
- Aturan:
  - **`detect_danger`**, urutan pemeriksaan:
    1. URL mengandung `/signin` atau `/login` → `DangerSignal("login", url)`;
    2. URL atau salah satu `frame_urls` mengandung `CAPTCHA_MARKERS` → `"captcha"`;
    3. `body_text` (huruf kecil) mengandung `VERIFY_TEXTS` → `"verifikasi"`;
    4. ada 429 di `http_statuses` → `"http_429"`, ada 403 → `"http_403"`;
    5. selain itu `None`.
  - **`has_results_for`** = ada respons `is_results_for`. **`has_related_for`** = `related_rows_for(...) is not None`.
  - **`__init__`** mendaftarkan `context.on("response", …)`:
    - setiap respons `etsy.com` yang path-nya mengandung `/marketplace-insights/` dan content-type-nya JSON → `CapturedResponse(url, status, parsed JSON atau None)` ditambahkan ke daftar internal;
    - setiap respons `etsy.com` dengan status 403/429 dan `request.resource_type` `document`/`xhr`/`fetch` → statusnya ditambahkan ke `_http_statuses`;
    - error membaca body diabaikan.
  - **`open()`**:
    1. `_http_statuses` dikosongkan, `page = context.new_page()`, lalu `goto(dashboard_url, wait_until="domcontentloaded")`.
    2. Kalau `"signin"` ada di URL → `NotLoggedIn`.
    3. Tunggu `uniform(settle_seconds)` lewat `page.wait_for_timeout`.
    4. Klik `NAV_SELECTOR` (tunggu terlihat ≤ 10 detik). Kalau menu tidak ada, `goto(INSIGHTS_URL)` dengan log "menu tidak ditemukan, membuka langsung".
    5. Tunggu `domcontentloaded`. Kalau `"signin"` ada di URL → `NotLoggedIn`.
    6. Playwright `TimeoutError` → `PageLoadTimeout`; error target tertutup → `BrowserClosed`.
  - **`search(keyword)`**:
    1. `mark = len(captured)`, `_http_statuses` dikosongkan.
    2. Cari kotak pencarian (selector pertama yang terlihat dalam `input_timeout`). Kalau tidak ada → `PageLoadTimeout("Kotak pencarian tidak ditemukan")`.
    3. Klik di posisi acak di dalam kotak (`position` = 20–80% lebar dan 30–70% tinggi).
    4. Hapus isi: `Meta+A` (di macOS) atau `Control+A`, lalu `Backspace`.
    5. Ketik per huruf dengan `page.keyboard.type(ch)` dan `page.wait_for_timeout(pacer.typing_delay_ms())`, lalu `Enter`.
    6. Tunggu (loop `wait_for_timeout(250)`) sampai `has_results_for(captured[mark:], keyword)`. Berhenti lebih awal kalau ada `_http_statuses` atau URL berisi `signin`. Kalau lewat `results_timeout` tanpa hasil dan tanpa tanda itu → `PageLoadTimeout`.
    7. Kalau hasil ada, tunggu `has_related_for` paling lama `related_timeout` (tidak fatal).
    8. Kembalikan `RawResult(keyword, page.url, tuple(captured[mark:]), "")`.
    9. Error target tertutup → `BrowserClosed`.
  - **`check_danger()`** = `detect_danger(page.url, [f.url for f in page.frames], innerText body (≤ 20.000 karakter, lewat page.evaluate), _http_statuses)`. Error target tertutup → `BrowserClosed`.
  - **`dwell(seconds, scroll)`**: tunggu dalam potongan 1 detik. Kalau `scroll`, lakukan 2–3 kali `page.mouse.wheel(0, rng.randint(200, 600))` yang tersebar di dalam waktu tunggu.

- [ ] **Step 1: Tulis test yang gagal**

`tests/test_insights_page.py` (unit, tanpa browser):
```python
from etsy_insights.insights_page import detect_danger, has_related_for, has_results_for
from tests.test_parser import load_raw

def test_detect_danger_cases():
    assert detect_danger("https://www.etsy.com/signin?from=x", [], "", []).kind == "login"
    assert detect_danger("https://www.etsy.com/your/shops/me/marketplace-insights", ["https://geo.captcha-delivery.com/captcha/?a=1"], "", []).kind == "captcha"
    assert detect_danger("https://www.etsy.com/x", [], "Please verify you are a human", []).kind == "verifikasi"
    assert detect_danger("https://www.etsy.com/x", [], "", [200, 429]).kind == "http_429"
    assert detect_danger("https://www.etsy.com/x", [], "", [403]).kind == "http_403"
    assert detect_danger("https://www.etsy.com/your/shops/me/marketplace-insights", [], "Searches 43k", [200]) is None

def test_has_results_for():
    raw = load_raw("custom")
    assert has_results_for(raw.responses, "custom") and not has_results_for(raw.responses, "hoodie")

def test_has_related_for_ignores_stale_poll():
    raw = load_raw("sweatshirt")
    stale_only = tuple(r for r in raw.responses if "enqueue" not in r.url)
    assert has_related_for(raw.responses, "sweatshirt") and not has_related_for(stale_only, "sweatshirt")
```

`tests/test_insights_page_smoke.py` (`@pytest.mark.smoke`, di-skip tanpa `CHROME_SMOKE_PATH`):
- Satu fixture modul meluncurkan Chromium headless lewat `ensure_chrome(9342, tmp_path_factory, Path(CHROME_SMOKE_PATH), ["--headless=new", "--no-sandbox"])` dan `connected_browser`. Di akhir modul, Chrome dimatikan dengan `pkill -f remote-debugging-port=9342`.
- Setiap test membuat `EtsyInsightsPage(context, Pacer(Config(kecepatan_ketik_ms=(1, 1)), random.Random(1)), random.Random(1), settle_seconds=(0, 0), input_timeout=1, results_timeout=5, related_timeout=2)`.
- Setiap test memasang `context.route("https://www.etsy.com/**", handler)` dan `context.route("https://geo.captcha-delivery.com/**", blank)`. `handler` membaca dict `state`:
  - `/your/shops/me/dashboard` → HTML berisi `<a data-app-key="marketplace-insights" href="/your/shops/me/marketplace-insights?ref=seller-platform-mcnav">Marketplace Insights</a>`;
  - path yang diawali `/your/shops/me/marketplace-insights` →
    - `INSIGHTS_HTML`: input `aria-label="Input to search for keywords"`, dan saat `Enter` memanggil `fetch(".../shop/12345678/marketplace-insights/results-data?query="+q+"&search_term_hash=&search_trigger=results_search_bar")` lalu `fetch(".../llm-exploratory-keywords/search/enqueue", {method: "POST"})`;
    - `CAPTCHA_HTML` (`<iframe src="https://geo.captcha-delivery.com/captcha/?x=1">`) kalau `state["captcha"]`;
    - HTML tanpa input kalau `state["no_input"]`;
  - `…/results-data` → body `results-data` dari fixture `sweatshirt.json` dengan status `state.get("results_status", 200)`;
  - `…/search/enqueue` → body enqueue dari fixture `sweatshirt.json`;
  - selain itu → 404.
- Test:
  - `test_open_and_search_returns_parsable_results`: `open()`, lalu `raw = search("sweatshirt")`. Assert `parse_search(raw).main.search_volume == 46395`, `len(parse_search(raw).related) == 180`, `check_danger() is None`, dan nilai input di halaman `== "sweatshirt"`.
  - `test_open_not_logged_in`: `dashboard_url="https://www.etsy.com/signin?from=test"`, lalu `open()` melempar `NotLoggedIn`.
  - `test_captcha_frame_detected`: `state["captcha"] = True`, `open()`, lalu `check_danger().kind == "captcha"`.
  - `test_http_429_detected_quickly`: `state["results_status"] = 429`, `search("sweatshirt")` selesai < 5 detik tanpa exception, dan `check_danger().kind == "http_429"`.
  - `test_search_box_missing_raises_page_load_timeout`: `state["no_input"] = True`, `open()`, lalu `search("x")` melempar `PageLoadTimeout`.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_insights_page.py -q`. Expected: FAIL (`etsy_insights.insights_page` belum ada).
- [ ] **Step 3: Implementasi `etsy_insights/insights_page.py`** sesuai aturan di atas.
- [ ] **Step 4: Jalankan unit + smoke**

Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`
Expected: semua PASS (smoke: 2 lama + 5 baru).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: real Marketplace Insights page driver with danger detection"
```

---

### Task 8: Perintah `run`, `mulai.command`, log, kunci sesi, README, paket

**Files:**
- Modify: `etsy_insights/__main__.py`, `README.md`, `tests/test_cli.py`
- Create: `mulai.command`

**Interfaces:**
- Consumes: semua unit di atas; `ensure_chrome`, `connected_browser` (Tahap 1); `parse_search`, `PARSER_VERSION` (Task 4); `EtsyInsightsPage` (Task 7); `run_session`, `format_summary`, `REASON_TEXT`, `SessionDeps` (Task 6); `upcoming` (Task 3).
- Produces:
  - `main(argv=None, *, base_dir=None, now=None, input_fn=input) -> int` dengan subcommand baru `run [--uji] [--abaikan-pendinginan]`.
  - `@contextmanager def _open_insights(cfg: Config, pacer: Pacer, rng: random.Random, log) -> Iterator[InsightsPage]`, yaitu `ensure_chrome` → `connected_browser` → `EtsyInsightsPage(context, pacer, rng, log=log)`. Ini titik injeksi untuk test.
  - `@contextmanager def session_lock(path: Path) -> Iterator[bool]`: `fcntl.flock(LOCK_EX | LOCK_NB)` pada `data/sesi.lock`, menghasilkan `False` kalau sedang dikunci, dan selalu dilepas.
  - `@contextmanager def interrupt_on_signals() -> Iterator[None]`: selama blok berjalan, SIGTERM dan SIGHUP melempar `KeyboardInterrupt`; handler lama dipulihkan sesudahnya.
- Alur `run`:
  1. `load_config`, buka store, sinkronkan `keywords.txt`.
  2. `session_lock`. Kalau terkunci → cetak "Sesi lain sedang berjalan. Tunggu sampai selesai." dan return 1.
  3. Kalau `--abaikan-pendinginan` dan cooldown aktif → cetak peringatan, lalu `input_fn("Ketik YA untuk tetap menjalankan: ")`. Selain `"YA"` → cetak "Dibatalkan." dan return 1.
  4. Buat file log `logs/sesi-YYYYMMDD-HHMMSS.log`. Fungsi `log` mencetak ke layar dan menulis baris `HH:MM:SS pesan` ke file.
  5. `rng = random.Random()`, `pacer = Pacer(cfg, rng)`.
  6. Di dalam `interrupt_on_signals()` dan `_open_insights(...)`: `run_session(SessionDeps(store, page, parse_search, pacer, cfg, now_fn, time.sleep, log, PARSER_VERSION), max_keywords=3 if --uji else None, ignore_cooldown=flag)`.
  7. Cetak `format_summary`, lalu return 0.
- Perubahan lain:
  - `status` ditambah jumlah `harvested` ("N hasil panen"). Alasan berhenti terakhir dicetak lewat `REASON_TEXT` kalau dikenal. Teks "keyword dicek" tetap.
  - `export` memakai `upcoming(store, cfg)` untuk sheet Antrean.
  - `mulai.command` mengikuti pola `kenali.command` dan menjalankan `.venv/bin/python -m etsy_insights run "$@"`.
  - README:
    - Tahap 2: tambah `keywords.txt`, `bash mulai.command --uji` sekali, lalu `bash mulai.command` setiap hari, dan `bash export.command`.
    - Arti alasan berhenti dan masa pendinginan.
    - Kuota 15 pencarian per hari.
    - Hapus catatan "Status: Tahap 1".

- [ ] **Step 1: Tulis test yang gagal di `tests/test_cli.py`**

```python
import fcntl, os, signal
import pytest
import etsy_insights.__main__ as cli
from contextlib import contextmanager
from tests.helpers import FakeClock, FakePage, fake_parse

def patch_page(monkeypatch, page):
    @contextmanager
    def fake_open(cfg, pacer, rng, log):
        yield page
    monkeypatch.setattr(cli, "_open_insights", fake_open)
    monkeypatch.setattr(cli, "parse_search", fake_parse)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)

def test_cli_run_uji(tmp_path, capsys, monkeypatch):
    page = FakePage(FakeClock(T0)); patch_page(monkeypatch, page)
    assert main(["run", "--uji"], base_dir=project(tmp_path, keywords="a\nb\nc\nd\n"), now=lambda: T0) == 0
    out = capsys.readouterr().out
    assert "Keyword dicek: 3" in out and page.searched == ["a", "b", "c"]
    assert len(list((tmp_path / "logs").glob("sesi-*.log"))) == 1

def test_cli_run_refuses_when_locked(tmp_path, capsys, monkeypatch):
    page = FakePage(FakeClock(T0)); patch_page(monkeypatch, page)
    base = project(tmp_path); (base / "data").mkdir()
    with open(base / "data" / "sesi.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["run"], base_dir=base, now=lambda: T0) == 1
    assert "Sesi lain sedang berjalan" in capsys.readouterr().out and page.opened == 0

def test_lock_released_after_error(tmp_path, monkeypatch):
    page = FakePage(FakeClock(T0)); patch_page(monkeypatch, page)
    page.search = lambda kw: (_ for _ in ()).throw(RuntimeError("aneh"))
    base = project(tmp_path)
    assert main(["run"], base_dir=base, now=lambda: T0) == 1
    with cli.session_lock(base / "data" / "sesi.lock") as ok:
        assert ok

def test_cli_ignore_cooldown_requires_ya(tmp_path, capsys, monkeypatch):
    from etsy_insights.store import Store
    base = project(tmp_path)
    s = Store(base / "data" / "etsy.db"); sid = s.start_session(T0)
    s.end_session(sid, T0, "tanda_bahaya", T0 + timedelta(hours=24)); s.close()
    page = FakePage(FakeClock(T0)); patch_page(monkeypatch, page)
    assert main(["run", "--abaikan-pendinginan"], base_dir=base, now=lambda: T0, input_fn=lambda p: "tidak") == 1
    assert page.opened == 0
    assert main(["run", "--abaikan-pendinginan"], base_dir=base, now=lambda: T0, input_fn=lambda p: "YA") == 0
    assert page.opened == 1

def test_sigterm_becomes_keyboard_interrupt():
    with pytest.raises(KeyboardInterrupt):
        with cli.interrupt_on_signals():
            os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
```

Tambahkan juga `"mulai.command"` ke daftar di `test_command_scripts_are_valid_and_executable`, dan tambahkan `from datetime import timedelta` di bagian import file.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_cli.py -q`. Expected: FAIL (`run` belum ada).
- [ ] **Step 3: Implementasi** `__main__.py`, `mulai.command` (`chmod +x`), dan README sesuai alur di atas.
- [ ] **Step 4: Jalankan semua test + smoke**

Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`
Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: run command with lock, logs, signal handling; mulai.command and README"
```

---

### Task 9: Profil selera (spec §16.8) + paket

**Files:**
- Create: `etsy_insights/taste.py`, `tests/test_taste.py`
- Modify: `etsy_insights/store.py`, `etsy_insights/export.py`, `etsy_insights/__main__.py`, `README.md`, `tests/test_store.py`, `tests/test_export.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `is_results_for` (Task 4), `RawResult`/`CapturedResponse` (Tahap 1), fixture `tests/fixtures/*.json` dan `load_raw` (Task 4), `export_excel` (Task 5), CLI `export` (Task 8).
- Produces (`taste.py`):
  ```python
  @dataclass(frozen=True)
  class ListingCard: title: str; price_text: str; price_value: float | None; reviews: int | None
                     bestseller: bool; star_seller: bool; shop: str; url: str
  @dataclass(frozen=True)
  class TasteProfile:
      keyword: str; listing_count: int; top_terms: tuple[tuple[str, int], ...]
      paid_price_low: str | None; paid_price_high: str | None
      listing_price_low: str | None; listing_price_high: str | None
      median_reviews: int | None; bestseller_share: float; star_seller_share: float; unique_shops: int
      difficulty: str          # "Mudah" | "Sedang" | "Sulit" | "Tidak diketahui"
      examples: tuple[ListingCard, ...]   # 5 kartu pertama
  def parse_price(text: str | None) -> float | None    # "Rp 712,738" -> 712738.0 ; "US$15.30" -> 15.3 ; ""/None -> None
  def top_terms(titles: Sequence[str], keyword: str, limit: int = 10) -> list[tuple[str, int]]
  def difficulty(median_reviews: int | None, bestseller_share: float, star_seller_share: float) -> str
  def build_profile(raw: RawResult) -> TasteProfile | None   # None bila tidak ada results-data atau kartu
  def build_profiles(store: Store) -> dict[str, TasteProfile]
  ```
- Produces (`store.py`): `latest_search_raws(self) -> dict[int, RawResult]`, yaitu keyword_id → `RawResult` dari baris `kind='search'` terbaru yang punya `raw_json` (direkonstruksi dari JSON).
- Produces (`export.py`):
  - `SELERA_HEADERS = ["Keyword", "Skor", "Label", "Harga dibayar pembeli", "Harga listing teratas", "Kesulitan masuk", "Median ulasan teratas", "% Bestseller", "% Star Seller", "Toko berbeda", "Tema populer", "Contoh 1", "Contoh 2", "Contoh 3", "Contoh 4", "Contoh 5"]`.
  - `PELUANG_HEADERS` ditambah `"Harga pasar"` dan `"Kesulitan masuk"` di akhir.
  - `export_excel(..., profiles: Mapping[str, TasteProfile] | None = None)` (keyword arg).
- Aturan:
  - **`top_terms`**:
    - Token = `[a-z]+` dari judul berhuruf kecil, minimal 3 huruf.
    - Buang `STOPWORDS = {"and", "are", "for", "from", "the", "this", "with", "you", "your", "our", "its", "gift", "gifts", "custom", "personalized", "personalised", "handmade"}`, dan buang kata dari keyword beserta bentuk `+s`. Kata penerima (mom, dog, kids, her, …) sengaja **tidak** dibuang karena menunjukkan selera.
    - Hitung frekuensi dokumen untuk unigram dan bigram (pasangan token berurutan setelah penyaringan). Ambil yang df ≥ 2.
    - Urutkan: df menurun, bigram lebih dulu, lalu alfabet.
    - Buang unigram yang menjadi bagian dari bigram terpilih dengan df yang sama. Potong ke `limit`.
  - **`difficulty`**:
    - `None` → `"Tidak diketahui"`;
    - `median ≥ 2000` atau (`bestseller ≥ 0.8` dan `median ≥ 1000`) → `"Sulit"`;
    - `median < 300` dan `bestseller < 0.5` → `"Mudah"`;
    - selain itu `"Sedang"`.
  - **`build_profile`** memakai respons `is_results_for` terakhir. Median ulasan dihitung dari kartu yang `numberOfReviews`-nya berupa angka.
  - **Excel:**
    - Urutan sheet: `Peluang`, `Selera`, `Semua data`, `Antrean`.
    - Sheet Selera berisi satu baris per profil, diurutkan sama seperti Peluang (keyword layak menurut skor, lalu sisanya menurut abjad). Baris info: `f"Profil selera untuk {n} keyword yang sudah dicari (±20 listing teratas di Marketplace Insights)."`.
    - Kolom **Tema populer** = `"christmas (7), vintage (6), …"`. Kolom **%** memakai format `0%`.
    - Kolom **Contoh i** = `f"{judul[:80]} | {harga} | {ulasan} ulasan"` dengan `cell.hyperlink = url`.
    - Kolom **Harga pasar** di Peluang = `f"{low} – {high}"` kalau ada, dan **Kesulitan masuk** = `difficulty`; keduanya `""` kalau tidak ada profil.
    - CLI `export` memanggil `build_profiles(store)`.

- [ ] **Step 1: Tulis test yang gagal**

`tests/test_taste.py`:
```python
import pytest
from etsy_insights.taste import build_profile, difficulty, parse_price, top_terms
from tests.test_parser import load_raw

def test_parse_price():
    assert parse_price("Rp 712,738") == 712738.0 and parse_price("US$15.30") == 15.3
    assert parse_price("") is None and parse_price(None) is None

def test_top_terms_prefers_phrases():
    titles = ["Retro Christmas Sweater Gift", "Retro Christmas Mug", "Vintage Retro Tee"]
    assert top_terms(titles, "sweater") == [("retro", 3), ("retro christmas", 2)]

def test_difficulty_rules():
    assert difficulty(2500, 0.1, 0.1) == "Sulit" and difficulty(1200, 0.85, 0.0) == "Sulit"
    assert difficulty(250, 0.3, 0.9) == "Mudah" and difficulty(650, 1.0, 0.5) == "Sedang"
    assert difficulty(None, 0.0, 0.0) == "Tidak diketahui"

def test_profile_sweatshirt():
    p = build_profile(load_raw("sweatshirt"))
    assert (p.listing_count, p.paid_price_low, p.paid_price_high) == (19, "US$15.30", "US$18.70")
    assert (p.median_reviews, p.unique_shops, p.difficulty) == (2362, 18, "Sulit")
    assert p.bestseller_share == pytest.approx(16 / 19) and p.star_seller_share == pytest.approx(16 / 19)
    terms = [t for t, _ in p.top_terms]
    assert "christmas" in terms[:3] and not any("sweatshirt" in t for t in terms)
    assert len(p.examples) == 5 and p.examples[0].title.startswith("Oh What Fun Christmas Sweatshirt")
    assert p.examples[0].url.startswith("https://www.etsy.com/listing/")

def test_profile_custom_and_personalized_difficulty():
    assert build_profile(load_raw("custom")).difficulty == "Sedang"
    assert build_profile(load_raw("personalized")).difficulty == "Sulit"

def test_profile_none_without_cards():
    assert build_profile(load_raw("swearshirt")) is None
```

`tests/test_store.py`:
```python
def test_latest_search_raws_roundtrip():
    from tests.test_parser import load_raw
    s = new_store("sweatshirt"); kid = s.get("sweatshirt").id
    raw = load_raw("sweatshirt")
    s.save_result(kid, make_metrics(), raw, T0, "t")
    back = s.latest_search_raws()[kid]
    assert back.keyword == "sweatshirt" and back.responses == raw.responses
```

`tests/test_export.py`:
- Ganti harapan `PELUANG_HEADERS` (otomatis lewat konstanta).
- Tambah:
```python
from etsy_insights.export import SELERA_HEADERS
from etsy_insights.taste import build_profile
from tests.test_parser import load_raw

def test_export_selera_sheet(tmp_path):
    rows = [make_row("sweatshirt", 46395, 0, 1863632), make_row("mug", 900, 2, 500)]
    profiles = {"sweatshirt": build_profile(load_raw("sweatshirt"))}
    wb = load_workbook(export_excel(score_all(rows, Config()), rows, [], tmp_path, T0.date(), profiles=profiles))
    assert wb.sheetnames == ["Peluang", "Selera", "Semua data", "Antrean"]
    sel = wb["Selera"]
    assert [c.value for c in sel[2]] == SELERA_HEADERS and sel.max_row == 3
    row = {h: sel.cell(3, i + 1) for i, h in enumerate(SELERA_HEADERS)}
    assert row["Keyword"].value == "sweatshirt" and row["Harga dibayar pembeli"].value == "US$15.30 – US$18.70"
    assert row["Kesulitan masuk"].value == "Sulit" and row["Contoh 1"].hyperlink.target.startswith("https://www.etsy.com/listing/")
    pel = wb["Peluang"]
    by_kw = {pel.cell(r, 1).value: [c.value for c in pel[r]] for r in range(3, pel.max_row + 1)}
    assert by_kw["sweatshirt"][-2:] == ["US$15.30 – US$18.70", "Sulit"] and by_kw["mug"][-2:] == [None, None]
```

`tests/test_cli.py`:
```python
def test_cli_export_includes_selera(tmp_path, capsys):
    from etsy_insights.store import Store
    from tests.test_parser import load_raw
    from tests.helpers import make_metrics
    base = project(tmp_path, keywords="sweatshirt\n")
    s = Store(base / "data" / "etsy.db"); s.sync_user_keywords(["sweatshirt"], T0)
    s.save_result(s.get("sweatshirt").id, make_metrics(volume=46395, level=0, comp=1863632), load_raw("sweatshirt"), T0, "t"); s.close()
    assert main(["export"], base_dir=base, now=lambda: T0) == 0
    sel = load_workbook(tmp_path / "hasil" / "peluang-2026-11-11.xlsx")["Selera"]
    assert sel.cell(3, 1).value == "sweatshirt"
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_taste.py tests/test_store.py tests/test_export.py tests/test_cli.py -q`. Expected: FAIL (`etsy_insights.taste` belum ada).
- [ ] **Step 3: Implementasi** `taste.py`, `Store.latest_search_raws`, perubahan `export.py`, dan CLI `export`. README: tambah penjelasan singkat sheet "Selera" dan arti "Kesulitan masuk".
- [ ] **Step 4: Jalankan semua test + smoke**

Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`
Expected: semua PASS.

- [ ] **Step 5: Commit, lalu buat paket**

```bash
git add -A && git commit -m "feat: buyer-taste profile from top listings (Selera sheet)"
```

Run: `git archive --format=zip --prefix=etsy-insights/ -o /home/user/etsy-insights-tahap2.zip HEAD && zipinfo /home/user/etsy-insights-tahap2.zip | grep -E "\.command$"`
Expected: empat file `.command` dengan izin `-rwxr-xr-x`.
