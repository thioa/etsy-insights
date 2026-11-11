# Etsy Insights — Tahap 3 (Web App Lokal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Etsy Insights.app" di Mac membuka web app lokal (bahasa Inggris). Dari browser, pengguna
bisa memulai, memantau, dan menghentikan sesi, melihat peluang dan selera pembeli, serta mengelola
keyword dan pengaturan, tanpa Terminal.

**Architecture:**
- Server Flask di `127.0.0.1` dengan halaman Jinja dan sedikit JavaScript biasa.
- Sesi pencarian tetap dijalankan oleh CLI yang sudah ada, sebagai **proses terpisah**, lewat `SessionRunner`.
- Data berada di `APP_HOME` (ditentukan oleh variabel lingkungan `ETSY_INSIGHTS_HOME`).
- Peluncur `.app` berupa skrip bash kecil ditambah `bootstrap.py` (hanya stdlib) yang menyiapkan venv, mengimpor data lama, menyalakan server, dan membuka browser.

**Tech Stack:** Python ≥ 3.11, Flask 3, Jinja2, `playwright`, `openpyxl`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-11-etsy-insights-web-app-design.md`. Spec scraper
(`2026-11-11-etsy-insights-scraper-design.md`, termasuk §16) tetap berlaku untuk semua aturan sesi.

**Mockup:** https://claude.ai/artifact/3aeWGE9RQDnyyqgJhuGuv9

**Branch:** `tahap-3`, dibuat dari `tahap-2`.

## Global Constraints

- Python ≥ 3.11. Dependensi runtime: `playwright>=1.48,<2`, `openpyxl>=3.1,<4`, `flask>=3,<4`. Dependensi dev: `pytest>=8`. `bootstrap.py` hanya memakai stdlib.
- **Semua teks produk dalam bahasa Inggris**, memakai istilah persis dari spec §3. README berbahasa Indonesia. Kode alasan berhenti di database **tidak berubah**.
- Server hanya `127.0.0.1`. Setiap POST wajib membawa token per peluncuran, Host harus `127.0.0.1:<port>` atau `localhost:<port>`, dan Origin (kalau ada) harus asal yang sama.
- Server web tidak pernah menjalankan Playwright atau menghubungi Etsy. Sesi selalu berupa proses `python -m etsy_insights run …`.
- Semua aturan keamanan sesi Tahap 1–2 tidak berubah.
- Tes tidak menghubungi etsy.com atau situs eksternal.
- Test: `.venv/bin/pytest -q`. Tes dengan Chromium asli: `CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`.

## Review Focus

1. **Situs lain di browser mencoba memicu `localhost:8765`** (CSRF / DNS rebinding) → harus 403. Dites di Task 5 `test_post_requires_token_host_and_origin`.
2. **Server membaca saat proses sesi sedang menulis database** → pembacaan tidak boleh gagal "database is locked". Dites di Task 2 `test_store_reads_while_other_connection_writes`.
3. **Stop ditekan saat sesi macet atau mengabaikan SIGTERM** → setelah batas waktu, proses dimatikan paksa dan status kembali "not running". Dites di Task 4 `test_stop_kills_after_timeout`.
4. **`keywords.txt` yang diedit tangan** (komentar, huruf besar, baris kosong) tetap utuh saat UI menambah atau menghapus keyword. Dites di Task 3 `test_remove_keeps_comments_and_other_lines`.
5. **Ikon dibuka saat server sudah jalan, atau port dipakai program lain** → hanya membuka tab baru, atau menampilkan dialog yang jelas. Dites di Task 7 `test_main_reuses_running_server` dan `test_main_reports_foreign_port`.

---

### Task 1: Semua teks produk ke bahasa Inggris

**Files:**
- Modify: `etsy_insights/models.py`, `score.py`, `taste.py`, `export.py`, `session.py`, `config.py`, `__main__.py`, `recorder.py`, `browser.py`, `insights_page.py`, `parser.py`, `config.toml`, `setup.command`, `kenali.command`, `export.command`, `mulai.command`
- Modify tests: `tests/test_score.py`, `test_taste.py`, `test_export.py`, `test_session.py`, `test_cli.py`, `test_config.py`

**Interfaces (nilai pasti):**
- `CONVERSION_LEVEL_TEXT = {0: "Very low", 1: "Low", 2: "Typical", 3: "High", 4: "Very high"}`.
- `score.label_for` → `"Gold" | "Potential" | "Skip"`. Baris tidak layak → `"Not enough data"`. `LEVEL_LABELS = {1: "Low", 2: "Medium", 3: "High"}`.
- `taste.difficulty` → `"Easy" | "Medium" | "Hard" | "Unknown"`.
- `export.py`:
  - Konstanta diganti nama:
    ```python
    OPPORTUNITIES_HEADERS = ["Keyword", "Searches/month", "Competing listings", "Conversion", "Conversion rate",
        "Searches per listing", "Score", "Label", "Week over week", "Source", "Date", "Market price", "Entry difficulty"]
    TASTE_HEADERS = ["Keyword", "Score", "Label", "Price buyers pay", "Top listing prices", "Entry difficulty",
        "Median reviews (top)", "% Bestseller", "% Star Seller", "Shops", "Popular themes",
        "Listing 1", "Listing 2", "Listing 3", "Listing 4", "Listing 5"]
    ALL_DATA_HEADERS = ["Keyword", "Data type", "Status", "Date", "Searches/month", "Competing listings",
        "Conversion", "Conversion rate", "Week over week", "Latest label"]
    QUEUE_HEADERS = ["#", "Keyword", "Source", "Depth", "Harvested from"]
    STATUS_TEXT = {"pending": "Queued", "in_progress": "Searching", "done": "Searched", "no_data": "No data",
                   "failed": "Failed", "harvested": "Harvested"}
    LABEL_FILLS = {"Gold": "FFD966", "Potential": "C6EFCE", "Skip": "D9D9D9"}
    ```
  - Nama sheet: `Opportunities`, `Buyer taste`, `All data`, `Queue`.
  - Kolom Source: `"Your list"`, `f"Harvested from: {p}"`, `f"Searched (from: {p})"`. Source di sheet Queue: `"Your list"` / `"Harvested"`. Data type: `"Harvested"` / `"Searched"`.
  - Baris info:
    - `f"Updated {today}. {n} keywords ranked."`, ditambah `" Few data yet (< 10 ranked keywords): ranking is rough."` kalau n < 10;
    - `f"Updated {today}. {n} rows."`;
    - `f"Updated {today}. Next {n} keywords to search."`;
    - `f"Buyer taste for {n} searched keywords (about 20 top listings each in Marketplace Insights)."`.
  - Contoh listing: `f"{title[:80]} | {price} | {reviews} reviews"`.
- `session.py`:
  - `REASON_TEXT` persis seperti tabel spec §3.
  - `SessionSummary` ditambah field terakhir `test_run: bool = False` (True kalau `max_keywords` tidak None).
  - `format_summary`:
    ```
    Session finished: {reason}    (QUOTA + test_run -> "Test run finished ({checked} searches).")
    Keywords checked: {checked} (ok {succeeded}, no data {no_data}, failed {failed})
    New keywords found: {new_keywords}
    Queue left: {queue_left}
    Searches left today: {quota_left}
    Warning: {kind} ({detail})            # kalau ada danger
    Cooldown until: {YYYY-MM-DD HH:MM}    # kalau ada cooldown
    ```
  - Log sesi:
    - `"Stopped: {reason}"`
    - `"Break {s:.0f} seconds."`
    - `"Waiting {s:.0f} seconds since the last session."`
    - `"  {volume} searches, {n} related keywords ({new} new)"`
    - `"  page did not load: {kw}"`
    - `"  could not read data: {exc}"`
    - `"  Etsy quota: {remaining} of {total} left"`
    - `"Warning sign: {kind} ({detail}). Stopping."`
    - `"{n} keywords from an interrupted session went back to the queue."`
  - Format baris `"[n/m] keyword"` **tidak berubah**, karena `runner` membacanya.
- `config.py`:
  - Pesan peringatan berbentuk `"{key}: …"` dalam bahasa Inggris, dan tetap menyebut nama kunci.
  - `ConfigError`: `f"config.toml is not valid at line {line}: {exc}"`, serta `"config.toml is not UTF-8 text. Open it in TextEdit and save it as plain text (UTF-8)."`.
- `__main__.py`:
  - `"Queue: {p} queued, {h} harvested, {d} searched, {nd} no data, {f} failed"`
  - `"Today: {x}/{limit} searches (left {r})"`
  - `"Cooldown until: …"`
  - `"Last session: {time}, {n} keywords. {reason text}"`
  - `"Excel file: {path}"`
  - `"Another session is running. Wait until it finishes."`
  - Peringatan pendinginan: `"WARNING: cooldown is active until {t}. Etsy just showed a warning; continuing now adds risk to your account."`, prompt `"Type YES to run anyway: "` (yang diterima hanya `YES`), lalu `"Cancelled."`.
  - `"Chrome closed or not responding: {exc}\nRun the command again to retry."`
  - `"Unexpected error: {Type}: {exc}\nCopy this message and send it to Claude."`
  - `"\nStopped."`
  - Untuk kode `error`, `_reason_text` mengembalikan `REASON_TEXT` versi Inggris dari spec.
- `recorder.py`, `browser.py`, `insights_page.py`, `parser.py`, file `.command`, dan komentar `config.toml`: diterjemahkan dengan nada yang sama. `PortBusy` tetap menyebut `port_debug`, dan `ParseError` tetap menyebut keyword-nya.

- [ ] **Step 1: Perbarui test ke teks Inggris (RED)**
  - **Label:** `"Emas"` → `"Gold"`, `"Potensial"` → `"Potential"`, `"Lewati"` → `"Skip"`, `"Data kurang"` → `"Not enough data"`.
  - **Difficulty:** `"Sulit"` → `"Hard"`, `"Sedang"` → `"Medium"`, `"Mudah"` → `"Easy"`, `"Tidak diketahui"` → `"Unknown"`.
  - **Export:**
    - konstanta lama diganti konstanta baru;
    - harapan `"Tinggi"` → `"High"`;
    - `"daftar Anda"` → `"Your list"`;
    - `"panen dari: a"` → `"Harvested from: a"`;
    - `"0 keyword layak"` → `"0 keywords ranked"`;
    - `"Data masih sedikit"` → `"Few data yet"`;
    - `["panen", "hasil panen"]` → `["Harvested", "Harvested"]`;
    - `["dicari", "sudah dicari"]` → `["Searched", "Searched"]`;
    - nama sheet → `["Opportunities", "Buyer taste", "All data", "Queue"]`;
    - `"hasil panen"` di sheet Queue → `"Harvested"`;
    - kolom Selera dibaca lewat `TASTE_HEADERS` (`"Price buyers pay"`, `"Entry difficulty"`, `"Listing 1"`);
    - dua kolom terakhir Opportunities → `["US$15.30 – US$18.70", "Hard"]`.
  - **Session:** `"Keyword dicek: 3"` → `"Keywords checked: 3"`, `"Sisa kuota hari ini: 12"` → `"Searches left today: 12"`, `"Masa pendinginan sampai"` → `"Cooldown until"`. Tambah:
    ```python
    def test_format_summary_test_run():
        clock, store, page = setup("a", "b", "c", "d")
        s = run_session(make_deps(store, page, clock), max_keywords=3)
        assert s.test_run and format_summary(s).startswith("Session finished: Test run finished (3 searches).")
    ```
  - **CLI:**
    - `"Antrean: 2 menunggu"` → `"Queue: 2 queued"`;
    - `"Hari ini: 0/15 keyword dicek"` → `"Today: 0/15 searches"`;
    - `"Sesi lain sedang berjalan"` → `"Another session is running"`;
    - `"kesalahan tak terduga"` → `"unexpected error"` / `"Unexpected error"`;
    - `"baris 1"` → `"line 1"`;
    - di `test_cli_ignore_cooldown_requires_ya`: `"tidak"` → `"no"` dan `"YA"` → `"YES"`, lalu ganti nama tesnya menjadi `test_cli_ignore_cooldown_requires_yes`;
    - `test_cli_export_includes_selera` membaca sheet `"Buyer taste"`.
  - **Config:** `match=r"config\.toml.*line 1"`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest -q`. Expected: FAIL pada test-test yang diubah.
- [ ] **Step 3: Implementasi** semua teks sesuai Interfaces.
- [ ] **Step 4: Pastikan tidak ada teks Indonesia tersisa di kode produk**

  Run: `grep -rnE "Berhenti|keyword dicek|Sesi |Peringatan|Dibatalkan|Antrean|Hari ini|Ketik|Kesalahan|tidak valid|belum login|pencarian per" etsy_insights/ *.command config.toml | grep -v "^etsy_insights/.*#"`

  Expected: kosong, kecuali kode alasan (`kuota_tercapai` dan sejenisnya) dan nama kunci config. Lalu `.venv/bin/pytest -q` → semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: English product text (labels, Excel, CLI, session messages)"
```

---

### Task 2: Fondasi: paths, WAL, opsi CLI, port_web, pra-cek, penutupan tab

**Files:**
- Create: `etsy_insights/paths.py`, `tests/test_paths.py`
- Modify: `etsy_insights/store.py`, `config.py`, `config.toml`, `session.py`, `__main__.py`, `insights_page.py`, `tests/test_store.py`, `tests/test_config.py`, `tests/test_session.py`, `tests/test_cli.py`, `tests/test_insights_page_smoke.py`

**Interfaces:**
- Produces `paths.py`:
  ```python
  PROJECT_ROOT = Path(__file__).resolve().parent.parent
  ENV_HOME = "ETSY_INSIGHTS_HOME"
  def app_home() -> Path            # Path(os.environ[ENV_HOME]) bila di-set, selain itu PROJECT_ROOT
  def excel_dir(home: Path) -> Path # ENV_HOME di-set -> Path.home() / "Documents" / "Etsy Insights"; selain itu home / "hasil"
  ```
- `Store.__init__`: `sqlite3.connect(path, timeout=10, isolation_level=None)`. Untuk file (bukan `:memory:`) jalankan `PRAGMA journal_mode=WAL`.
- `Config.port_web: int = 8765`, dengan `HARD_LIMITS["port_web"] = (1024, 65535)`. Nilai di luar rentang memakai default dan memunculkan peringatan, sama seperti angka tidak valid lainnya. `config.toml` mendapat kunci ini.
- `session.precheck(store, cfg, now, max_keywords=None, ignore_cooldown=False) -> tuple[StopReason | None, datetime | None]`. Urutannya:
  1. cooldown (dilewati kalau `ignore_cooldown`) → `(COOLDOWN, until)`;
  2. sisa kuota 0 → `(NO_QUOTA, None)`;
  3. `"kuota_etsy"` hari ini → `(ETSY_QUOTA, None)`;
  4. `select_next(...) is None` → `(QUEUE_EMPTY, None)`;
  5. selain itu `(None, None)`.

  `run_session` memanggilnya (setelah `recover_in_progress`) dan berhenti **sebelum** `start_session`/`page.open()` kalau ada alasan.
- CLI `run`:
  - `--log-file PATH`: logger menulis ke PATH, bukan ke `logs/sesi-…`.
  - `--yes`: melewati prompt dan dianggap YES.
  - Default `base_dir` = `paths.app_home()`. `export` menulis ke `paths.excel_dir(base)`.
- `EtsyInsightsPage.close()` kini juga menutup tab yang dibukanya (`self._page.close()` kalau ada; error diabaikan).

- [ ] **Step 1: Tulis test yang gagal**

```python
# tests/test_paths.py
from pathlib import Path
from etsy_insights import paths

def test_app_home_default_and_env(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    assert paths.app_home() == paths.PROJECT_ROOT and paths.excel_dir(tmp_path) == tmp_path / "hasil"
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.app_home() == tmp_path / "home"
    assert paths.excel_dir(tmp_path / "home") == tmp_path / "Documents" / "Etsy Insights"
```
```python
# tests/test_store.py
def test_store_uses_wal(tmp_path):
    s = Store(tmp_path / "x.db")
    assert s._db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

def test_store_reads_while_other_connection_writes(tmp_path):
    s = Store(tmp_path / "x.db"); s.sync_user_keywords(["a"], T0)
    other = sqlite3.connect(tmp_path / "x.db", isolation_level=None)
    other.execute("BEGIN IMMEDIATE"); other.execute("UPDATE keywords SET fail_count = 1")
    assert s.get("a").fail_count == 0          # pembaca tidak terkunci
    other.execute("COMMIT")
    assert s.get("a").fail_count == 1
```
```python
# tests/test_config.py
def test_port_web_default_and_limits(tmp_path):
    assert Config().port_web == 8765
    cfg, warnings = load_config(write(tmp_path, "port_web = 80\n"))
    assert cfg.port_web == 8765 and any("port_web" in w for w in warnings)
```
```python
# tests/test_session.py
def test_precheck_queue_empty_does_not_open_chrome():
    clock = FakeClock(T0); store = Store(":memory:"); page = FakePage(clock)
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.QUEUE_EMPTY and page.opened == 0 and store.last_session() is None

def test_precheck_reports_reasons():
    from etsy_insights.session import precheck
    store = Store(":memory:"); store.sync_user_keywords(["a"], T0)
    assert precheck(store, Config(), T0) == (None, None)
    sid = store.start_session(T0); store.end_session(sid, T0, "tanda_bahaya", T0 + timedelta(hours=24))
    assert precheck(store, Config(), T0) == (StopReason.COOLDOWN, T0 + timedelta(hours=24))
    assert precheck(store, Config(), T0, ignore_cooldown=True) == (None, None)
```
```python
# tests/test_cli.py
def test_cli_run_log_file_and_yes(tmp_path, monkeypatch):
    from etsy_insights.store import Store
    page = FakePage(FakeClock(T0)); patch_page(monkeypatch, page)
    base = project(tmp_path, keywords="a\n")
    s = Store(base / "data" / "etsy.db"); sid = s.start_session(T0)
    s.end_session(sid, T0, "tanda_bahaya", T0 + timedelta(hours=24)); s.close()
    log = tmp_path / "x.log"
    def no_input(prompt):
        raise AssertionError("must not prompt")
    assert main(["run", "--abaikan-pendinginan", "--yes", "--log-file", str(log)], base_dir=base,
                now=lambda: T0, input_fn=no_input) == 0
    assert "[1/" in log.read_text(encoding="utf-8")
```
Smoke (`tests/test_insights_page_smoke.py`):
```python
def test_close_closes_its_tab(context, state):
    page = make_page(context); page.open()
    before = len(context.pages)
    page.close()
    assert len(context.pages) == before - 1
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest -q`. Expected: FAIL (`etsy_insights.paths` belum ada, dst.).
- [ ] **Step 3: Implementasi** sesuai Interfaces.
- [ ] **Step 4: Jalankan unit + smoke.** Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: app home paths, WAL store, CLI --log-file/--yes, session precheck, tab cleanup"
```

---

### Task 3: Kelola keyword dan pengaturan

**Files:**
- Create: `etsy_insights/keywords.py`, `etsy_insights/settings.py`, `tests/test_keywords.py`, `tests/test_settings.py`
- Modify: `etsy_insights/store.py` (`remove_user_keyword`), `config.toml` (dibuat dari `render_config(Config())`)

**Interfaces:**
- `keywords.py`:
  ```python
  @dataclass(frozen=True)
  class UserKeyword: keyword: str; status: str      # status store ("pending" bila belum ada di DB)
  def add_keywords(home: Path, store: Store, text: str, now: datetime) -> list[str]
  def remove_keyword(home: Path, store: Store, keyword: str) -> bool
  def prioritize(home: Path, store: Store, keyword: str, now: datetime) -> bool
  def list_user_keywords(home: Path, store: Store) -> list[UserKeyword]
  ```
  - `add_keywords`: normalisasi setiap baris; buang yang kosong, yang diawali `#`, dan yang sudah ada di `keywords.txt`. Tambahkan sisanya di akhir file (buat file kalau belum ada, pastikan diawali baris baru), lalu panggil `store.sync_user_keywords`. Mengembalikan daftar yang benar-benar baru.
  - `remove_keyword`: hanya untuk keyword dengan `source == "user"` dan `status == "pending"`. Hapus baris yang hasil normalisasinya sama (komentar dan baris lain tetap), lalu `store.remove_user_keyword(id)`. Mengembalikan False kalau tidak memenuhi syarat.
  - `prioritize`: False kalau keyword tidak ada di store. Selain itu `add_keywords(keyword)`, dan hasilnya True kalau keyword sekarang `pending` dengan source user.
- `Store.remove_user_keyword(keyword_id) -> None`: kalau keyword punya baris `panen`, ubah menjadi `source='related'`, `depth=1`, `status='harvested'`. Kalau tidak punya hasil sama sekali, hapus barisnya.
- `settings.py`:
  ```python
  FORM_FIELDS = ("kuota_harian", "jeda_min", "jeda_max", "durasi_sesi_menit",
                 "bobot_volume", "bobot_conversion", "bobot_kompetisi")
  def settings_form(cfg: Config) -> dict[str, str]
  def render_config(cfg: Config) -> str            # SEMUA kunci Config, komentar bahasa Inggris
  def save_settings(home: Path, form: Mapping[str, str]) -> tuple[Config | None, dict[str, str]]
  ```
  - Validasi (pesan per field, bahasa Inggris):
    - `kuota_harian`: bilangan bulat 1–30 → `"Enter a whole number from 1 to 30."`;
    - `jeda_min`: bilangan bulat ≥ 15 dan ≤ 600 → `"Enter seconds from 15 to 600."`;
    - `jeda_max`: ≥ `jeda_min` dan ≤ 600 → `"Must be at least the minimum pause and at most 600."`;
    - `durasi_sesi_menit`: 1–60 → `"Enter minutes from 1 to 60."`;
    - bobot: angka ≥ 0 → `"Enter a number of 0 or more."`, dan jumlahnya > 0 (error pada `bobot_volume`: `"At least one weight must be above 0."`).
  - Kalau valid: `cfg = replace(load_config(home/"config.toml")[0], …)` (bobot dinormalisasi), tulis `render_config(cfg)`, lalu kembalikan `(cfg, {})`. Kalau ada error: `(None, errors)` dan file tidak berubah.

- [ ] **Step 1: Tulis test yang gagal**

```python
# tests/test_keywords.py
from etsy_insights.keywords import add_keywords, list_user_keywords, prioritize, remove_keyword
from etsy_insights.store import Store
from tests.helpers import T0, make_metrics, make_raw, make_related

def home_with(tmp_path, text):
    (tmp_path / "keywords.txt").write_text(text, encoding="utf-8"); return tmp_path

def test_add_dedupes_and_appends(tmp_path):
    home = home_with(tmp_path, "# my list\nMug")
    s = Store(":memory:")
    assert add_keywords(home, s, "mug\n\n Tote Bag \n# note\ntote bag\n", T0) == ["tote bag"]
    assert (home / "keywords.txt").read_text(encoding="utf-8") == "# my list\nMug\ntote bag\n"
    assert s.get("tote bag").status == "pending"

def test_remove_keeps_comments_and_other_lines(tmp_path):
    home = home_with(tmp_path, "# my list\nMug\n\nTote Bag\n")
    s = Store(":memory:"); s.sync_user_keywords(["mug", "tote bag"], T0)
    assert remove_keyword(home, s, "tote bag")
    assert (home / "keywords.txt").read_text(encoding="utf-8") == "# my list\nMug\n\n"
    assert s.get("tote bag") is None

def test_remove_refuses_searched_and_restores_harvested(tmp_path):
    home = home_with(tmp_path, "a\n")
    s = Store(":memory:"); s.sync_user_keywords(["a"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    assert not remove_keyword(home, s, "a")
    s.save_harvest(s.get("a").id, [make_related("x")], 200, 2, T0)
    assert prioritize(home, s, "x", T0) and s.get("x").source == "user"
    assert remove_keyword(home, s, "x")
    x = s.get("x"); assert (x.source, x.depth, x.status) == ("related", 1, "harvested")

def test_prioritize_unknown_is_false_and_list_statuses(tmp_path):
    home = home_with(tmp_path, "a\nb\n")
    s = Store(":memory:"); s.sync_user_keywords(["a", "b"], T0)
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    assert not prioritize(home, s, "nope", T0)
    assert [(k.keyword, k.status) for k in list_user_keywords(home, s)] == [("a", "done"), ("b", "pending")]
```
```python
# tests/test_settings.py
from pathlib import Path
from etsy_insights.config import Config, load_config
from etsy_insights.settings import render_config, save_settings, settings_form

VALID = {"kuota_harian": "12", "jeda_min": "25", "jeda_max": "70", "durasi_sesi_menit": "40",
         "bobot_volume": "2", "bobot_conversion": "1", "bobot_kompetisi": "1"}

def test_shipped_config_is_rendered_default():
    assert Path("config.toml").read_text(encoding="utf-8") == render_config(Config())

def test_save_valid_settings_roundtrip_and_keeps_other_keys(tmp_path):
    (tmp_path / "config.toml").write_text("port_debug = 9333\n", encoding="utf-8")
    cfg, errors = save_settings(tmp_path, VALID)
    assert errors == {} and cfg.kuota_harian == 12 and cfg.jeda_antar_keyword_detik == (25, 70)
    loaded, warnings = load_config(tmp_path / "config.toml")
    assert loaded == cfg and warnings == [] and loaded.port_debug == 9333 and loaded.bobot == (0.5, 0.25, 0.25)
    assert settings_form(loaded)["kuota_harian"] == "12"

def test_save_rejects_out_of_range_without_writing(tmp_path):
    bad = dict(VALID, kuota_harian="40", jeda_min="10", jeda_max="5", durasi_sesi_menit="x",
               bobot_volume="0", bobot_conversion="0", bobot_kompetisi="0")
    cfg, errors = save_settings(tmp_path, bad)
    assert cfg is None and not (tmp_path / "config.toml").exists()
    assert set(errors) == {"kuota_harian", "jeda_min", "jeda_max", "durasi_sesi_menit", "bobot_volume"}
    assert "1 to 30" in errors["kuota_harian"]
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_keywords.py tests/test_settings.py -q`. Expected: FAIL (modul belum ada).
- [ ] **Step 3: Implementasi** sesuai Interfaces. `config.toml` = `render_config(Config())`.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: keyword list and settings management for the web app"
```

---

### Task 4: SessionRunner (menjalankan, memantau, dan menghentikan proses sesi)

**Files:**
- Create: `etsy_insights/runner.py`, `tests/fake_session.py`, `tests/test_runner.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class RunnerStatus:
    running: bool; source: str | None          # "app" | "terminal" | None
    current_keyword: str | None; done: int; limit: int | None
    log_tail: tuple[str, ...]; stopping: bool
class RunnerBusy(Exception): ...
def is_locked(lock_path: Path) -> bool                      # flock LOCK_EX|LOCK_NB lalu lepas; file belum ada -> False
def parse_progress(lines: Sequence[str]) -> tuple[str | None, int, int | None]   # dari baris "[n/m] keyword" terakhir
class SessionRunner:
    def __init__(self, home: Path, *, command: Sequence[str] | None = None, stop_timeout: float = 30.0,
                 popen=subprocess.Popen, clock=time.monotonic) -> None
    def start(self, test_run: bool = False, ignore_cooldown: bool = False) -> Path   # path log
    def stop(self) -> bool
    def status(self, tail: int = 20) -> RunnerStatus
```
Aturan:
- **Perintah default:** `[sys.executable, "-m", "etsy_insights", "run"]`, ditambah `--uji` (kalau `test_run`), `--abaikan-pendinginan --yes` (kalau `ignore_cooldown`), dan `--log-file <home>/logs/session-YYYYMMDD-HHMMSS.log`.
- **Lingkungan proses:** `env` = `os.environ` + `ETSY_INSIGHTS_HOME=home` + `PYTHONPATH=<folder induk paket etsy_insights>`. Stdout dan stderr diarahkan ke `<log>.out`, dengan `start_new_session=True`.
- **`start`:** `RunnerBusy("A session is already running.")` kalau proses milik runner masih hidup, atau kalau `is_locked(home/"data"/"sesi.lock")`.
- **`stop`:** SIGTERM ke proses milik runner dan catat batas waktunya. False kalau tidak ada proses.
- **`status`:**
  - **Proses milik runner:** `running = poll() is None`, `source = "app"`. Kalau sudah melewati batas waktu stop dan proses masih hidup, kirim SIGKILL lalu `wait`.
  - **Bukan proses runner tapi lock terpegang:** `running=True`, `source="terminal"`, dan log diambil dari `logs/*.log` terbaru.
  - **Ekor log:** baris non-kosong terakhir dari log aktif (atau log terakhir).

- [ ] **Step 1: Tulis `tests/fake_session.py` dan test yang gagal**

```python
# tests/fake_session.py — meniru `python -m etsy_insights run`
import signal, sys, time
from pathlib import Path
args = sys.argv[1:]
log = Path(args[args.index("--log-file") + 1])
def bye(*_):
    with log.open("a", encoding="utf-8") as f:
        f.write("12:00:03 Stopped: Stopped by you.\n")
    sys.exit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if "--ignore-term" in args else bye)
log.parent.mkdir(parents=True, exist_ok=True)
log.write_text("12:00:00 [1/3] alpha\n12:00:01   1000 searches, 5 related keywords (5 new)\n12:00:02 [2/3] beta\n",
               encoding="utf-8")
while True:
    time.sleep(0.05)
```
```python
# tests/test_runner.py
import fcntl, sys, time
from pathlib import Path
import pytest
from etsy_insights.runner import RunnerBusy, SessionRunner, parse_progress

FAKE = [sys.executable, str(Path(__file__).parent / "fake_session.py")]

def wait_for(cond, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond(): return True
        time.sleep(0.05)
    return False

def test_parse_progress():
    assert parse_progress(["10:00:00 [1/15] mug", "10:00:01   12 searches", "10:00:40 [2/15] tote bag"]) == ("tote bag", 2, 15)
    assert parse_progress([]) == (None, 0, None)

def test_start_status_stop(tmp_path):
    r = SessionRunner(tmp_path, command=FAKE)
    r.start(test_run=True)
    assert wait_for(lambda: r.status().current_keyword == "beta")
    st = r.status(); assert (st.running, st.source, st.done, st.limit) == (True, "app", 2, 3)
    with pytest.raises(RunnerBusy):
        r.start()
    assert r.stop()
    assert wait_for(lambda: not r.status().running)
    assert any("Stopped" in line for line in r.status().log_tail)

def test_stop_kills_after_timeout(tmp_path):
    r = SessionRunner(tmp_path, command=FAKE + ["--ignore-term"], stop_timeout=0.3)
    r.start()
    assert wait_for(lambda: r.status().done == 2)
    r.stop()
    assert wait_for(lambda: not r.status().running, timeout=5)

def test_terminal_session_detected(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "sesi-20261111-100000.log").write_text("10:00:00 [4/15] mug\n", encoding="utf-8")
    with open(tmp_path / "data" / "sesi.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = SessionRunner(tmp_path, command=FAKE)
        st = r.status()
        assert (st.running, st.source, st.current_keyword) == (True, "terminal", "mug")
        with pytest.raises(RunnerBusy):
            r.start()
    assert not SessionRunner(tmp_path, command=FAKE).status().running

def test_default_command_and_env(tmp_path):
    calls = []
    class P:
        pid = 1
        def poll(self): return None
    def fake_popen(args, **kw):
        calls.append((args, kw)); return P()
    r = SessionRunner(tmp_path, popen=fake_popen)
    log = r.start(test_run=True, ignore_cooldown=True)
    args, kw = calls[0]
    assert args[:4] == [sys.executable, "-m", "etsy_insights", "run"]
    assert "--uji" in args and "--abaikan-pendinginan" in args and "--yes" in args and args[-2:] == ["--log-file", str(log)]
    assert kw["env"]["ETSY_INSIGHTS_HOME"] == str(tmp_path) and kw["start_new_session"] is True
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_runner.py -q`. Expected: FAIL (`etsy_insights.runner` belum ada).
- [ ] **Step 3: Implementasi `etsy_insights/runner.py`.**
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: SessionRunner starts, watches and stops the session process"
```

---

### Task 5: Server web: keamanan, API, perintah `web`

**Files:**
- Create: `etsy_insights/web/__init__.py`, `web/security.py`, `web/api.py`, `tests/web_helpers.py`, `tests/test_web_api.py`, `tests/test_web_smoke.py`
- Modify: `requirements.txt` (`flask>=3,<4`), `etsy_insights/__main__.py` (subcommand `web`)

**Interfaces:**
- `create_app(home: Path, *, token: str, runner, port: int = 8765, now: Callable[[], datetime] | None = None, on_quit: Callable[[], None] | None = None) -> Flask`.
  - `runner` mengikuti antarmuka `SessionRunner` (`start`, `stop`, `status`).
  - `on_quit` default: `threading.Timer(0.5, os._exit, [0]).start()`.
  - `app.config["APP_TOKEN"] = token`.
  - `Store` dibuka per permintaan dari `home/"data"/"etsy.db"` dan ditutup di `teardown_appcontext`.
- **`security.py`** dipasang lewat `install(app, port)`:
  - `before_request` → 403 kalau `request.host` tidak termasuk `{f"127.0.0.1:{port}", f"localhost:{port}"}`.
  - Untuk metode selain GET/HEAD: 403 kalau `Origin` ada dan tidak termasuk `{f"http://127.0.0.1:{port}", f"http://localhost:{port}"}`, atau kalau token (header `X-App-Token`, field JSON `token`, atau field form `token`) tidak cocok (`secrets.compare_digest`).
  - Body 403 berupa JSON `{"error": "Forbidden"}`.
- **API JSON (`api.py`):**

  | Endpoint | Hasil |
  |---|---|
  | `GET /api/ping` | `{"ok": true, "app": "etsy-insights"}` |
  | `GET /api/status` | `{"runner": {running, source, current_keyword, done, limit, log_tail, stopping}, "today": {"searches", "limit"}, "collected": int, "queue": int, "account": {"state": "safe"\|"cooldown"\|"etsy_quota", "until": iso\|None, "message": str}, "last_session": null \| {"started_at", "checked", "reason_code", "reason_text"}, "can_start": bool, "blocker": str\|None}`. `collected` = jumlah keyword dengan baris hasil, `queue = len(upcoming(store, cfg, limit=10**9))`. |
  | `POST /api/session/start` `{"test_run", "ignore_cooldown", "confirm"}` | 409 `{"error"}` kalau runner sibuk (pesan `RunnerBusy`), atau kalau `precheck` memberi alasan. Pengecualian: alasan COOLDOWN dengan `ignore_cooldown` dan `confirm == "YES"`. Teks error = `REASON_TEXT`. Kalau lolos → `runner.start(...)`, `{"ok": true}`. |
  | `POST /api/session/stop` | `{"ok": runner.stop()}` |
  | `POST /api/keywords/add` `{"text"}` | `{"added": [...]}` |
  | `POST /api/keywords/remove` `{"keyword"}` | 200 `{"ok": true}`, atau 409 `{"error": "Only queued keywords from your list can be removed."}` |
  | `POST /api/keywords/prioritize` `{"keyword"}` | 200, atau 404 `{"error": "Unknown keyword."}` |
  | `POST /api/settings` `{fields}` | 200 `{"ok": true}`, atau 400 `{"errors": {...}}` |
  | `POST /api/quit` `{"confirm"}` | 409 `{"error": "A session is running. Stop it and quit?"}` kalau runner berjalan dari app dan `confirm` bukan true. Selain itu `runner.stop()` (kalau berjalan), `on_quit()`, lalu `{"ok": true}`. |
  | `GET /download/excel` | `export_excel(...)` ke `excel_dir(home)` dengan profil selera, lalu `send_file(..., as_attachment=True)` |
- **CLI `web [--port N]`:**
  - Port dari argumen atau `cfg.port_web`.
  - Kalau port sudah dipakai (`browser.port_in_use`), cetak `"Port {N} is in use. Change port_web in Settings or quit the other program."` lalu return 2.
  - Selain itu `token = secrets.token_urlsafe(32)` dan `create_app(...).run(host="127.0.0.1", port=N, threaded=True, use_reloader=False)`.
- **`tests/web_helpers.py`:**
  - `seeded_home(tmp_path) -> Path` mengisi `data/etsy.db` dengan 4 fixture (`personalized`, `sweatshirt`, `custom`, `swearshirt`), memakai `parse_search` + `save_result` + `save_harvest` persis seperti uji alur Tahap 2, lalu menulis `keywords.txt` berisi keempatnya.
  - `FakeRunner` dengan `.started` (list argumen), `.running`, `.stopped`, serta `status()` yang mengembalikan `RunnerStatus`.
  - `client(app)` = `app.test_client()` dengan `base_url="http://127.0.0.1:8765"`.
  - `TOKEN = "t" * 32`.

- [ ] **Step 1: Tulis test yang gagal (`tests/test_web_api.py`)**

```python
import pytest
from openpyxl import load_workbook
from etsy_insights.web import create_app
from tests.web_helpers import TOKEN, FakeRunner, client, seeded_home

H = {"X-App-Token": TOKEN}

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ETSY_INSIGHTS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    home = seeded_home(tmp_path / "home"); runner = FakeRunner(); quits = []
    app = create_app(home, token=TOKEN, runner=runner, on_quit=lambda: quits.append(1))
    return home, runner, quits, client(app)

def test_ping_and_status(setup):
    home, runner, quits, c = setup
    assert c.get("/api/ping").get_json() == {"ok": True, "app": "etsy-insights"}
    st = c.get("/api/status").get_json()
    assert st["today"]["limit"] == 15 and st["collected"] > 400 and st["account"]["state"] == "safe"
    assert st["can_start"] is True and st["runner"]["running"] is False

def test_post_requires_token_host_and_origin(setup):
    home, runner, quits, c = setup
    assert c.post("/api/session/start", json={}).status_code == 403
    assert c.post("/api/session/start", json={}, headers={**H, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/session/start", json={}, headers=H, base_url="http://evil.example:8765").status_code == 403
    assert c.get("/api/ping", base_url="http://evil.example:8765").status_code == 403
    assert runner.started == []
    assert c.post("/api/session/start", json={"test_run": True},
                  headers={**H, "Origin": "http://127.0.0.1:8765"}).status_code == 200
    assert runner.started == [{"test_run": True, "ignore_cooldown": False}]

def test_start_blocked_by_cooldown_unless_yes(setup):
    from datetime import datetime, timedelta
    from etsy_insights.store import Store
    home, runner, quits, c = setup
    s = Store(home / "data" / "etsy.db"); now = datetime.now().astimezone()
    sid = s.start_session(now); s.end_session(sid, now, "tanda_bahaya", now + timedelta(hours=24)); s.close()
    r = c.post("/api/session/start", json={}, headers=H)
    assert r.status_code == 409 and "Cooldown" in r.get_json()["error"]
    assert c.post("/api/session/start", json={"ignore_cooldown": True, "confirm": "yes"}, headers=H).status_code == 409
    assert c.post("/api/session/start", json={"ignore_cooldown": True, "confirm": "YES"}, headers=H).status_code == 200

def test_start_refused_when_runner_busy(setup):
    home, runner, quits, c = setup
    runner.running = True
    assert c.post("/api/session/start", json={}, headers=H).status_code == 409

def test_keywords_and_settings_api(setup):
    home, runner, quits, c = setup
    assert c.post("/api/keywords/add", json={"text": "Tote Bag\nmug"}, headers=H).get_json()["added"] == ["tote bag", "mug"]
    assert c.post("/api/keywords/remove", json={"keyword": "mug"}, headers=H).status_code == 200
    assert c.post("/api/keywords/remove", json={"keyword": "sweatshirt"}, headers=H).status_code == 409
    assert c.post("/api/keywords/prioritize", json={"keyword": "gift for her"}, headers=H).status_code == 200
    assert c.post("/api/keywords/prioritize", json={"keyword": "zzz"}, headers=H).status_code == 404
    r = c.post("/api/settings", json={"kuota_harian": "99"}, headers=H)
    assert r.status_code == 400 and "kuota_harian" in r.get_json()["errors"]

def test_quit_confirms_running_session(setup):
    home, runner, quits, c = setup
    runner.running = True
    assert c.post("/api/quit", json={}, headers=H).status_code == 409 and quits == []
    assert c.post("/api/quit", json={"confirm": True}, headers=H).status_code == 200
    assert runner.stopped and quits == [1]

def test_download_excel(setup, tmp_path):
    home, runner, quits, c = setup
    r = c.get("/download/excel")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    files = list((tmp_path / "Documents" / "Etsy Insights").glob("peluang-*.xlsx"))
    assert len(files) == 1 and load_workbook(files[0]).sheetnames[0] == "Opportunities"
```

**Smoke** `tests/test_web_smoke.py`: jalankan server sungguhan di thread (`werkzeug.serving.make_server("127.0.0.1", port, app)` pada port bebas). Aplikasinya memakai `SessionRunner(home, command=FAKE)` dari Task 4.
- `GET /api/ping` lewat `urllib` mengembalikan JSON yang benar.
- `POST /api/session/start` dengan token dan Host yang benar mengembalikan 200, lalu dalam 5 detik `status.runner.current_keyword == "beta"`.
- `POST /api/session/stop`, lalu dalam 5 detik `running` menjadi false.
- Di akhir, server dimatikan.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pip install -q "flask>=3,<4" && .venv/bin/pytest tests/test_web_api.py tests/test_web_smoke.py -q`. Expected: FAIL (`etsy_insights.web` belum ada).
- [ ] **Step 3: Implementasi** `web/__init__.py`, `security.py`, `api.py`, dan perintah `web`. Tambahkan Flask ke `requirements.txt`.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: local web server with token/host/origin protection and JSON API"
```

---

### Task 6: Halaman web (sesuai mockup, bahasa Inggris)

**Files:**
- Create: `etsy_insights/web/views.py`, `web/templates/{base,session,opportunities,keyword,keywords,settings,quit}.html`, `web/static/{app.css,app.js}`, `tests/test_web_pages.py`
- Modify: `etsy_insights/taste.py` (`ListingCard.image_url`), `etsy_insights/store.py` (`harvested_from`)

**Interfaces:**
- `ListingCard` ditambah field terakhir `image_url: str` (dari `imageUrl`, `""` kalau tidak ada).
- `Store.harvested_from(parent_id: int, limit: int = 50) -> list[ResultRow]`: hasil terbaru keyword yang `parent_id`-nya induk ini, diurutkan menurut `search_volume` menurun.
- `views.trend_points(values: Sequence[float], width: int = 760, height: int = 200) -> str`: `"x,y …"` dengan skala y 0..max(values)×1.1. Kosong → `""`.
- **Halaman:**
  - `GET /` (Session), `/opportunities`, `/keyword/<path:keyword>` (404 kalau tidak dikenal), `/keywords`, `/settings`.
  - `base.html` berisi `<meta name="app-token" content="{{ token }}">`, menu **Session · Opportunities · My keywords · Settings**, `app.css`, dan `app.js`.
- **Parameter `/opportunities`:**
  - `label` (berulang: Gold/Potential/Skip);
  - `difficulty` (berulang: Easy/Medium/Hard/Not searched yet; "Not searched yet" = tanpa profil);
  - `conv_min` (0–4);
  - `vol_min` (int);
  - `q` (substring);
  - `sort` (`score|volume|competition|conversion|keyword`), `dir` (`asc|desc`, default `score desc`);
  - `page` (50 per halaman).
  - Isi tabel: hanya baris layak (Gold/Potential/Skip), dengan profil dari `build_profiles`.
- **`app.js`:**
  - membaca token dari meta;
  - `[data-api]` pada form/tombol → `fetch` POST JSON dengan header `X-App-Token`; kalau berhasil, muat ulang halaman atau perbarui panel; kalau gagal, tampilkan `error`/`errors` di elemen `[data-error-for]`;
  - di halaman Session, polling `GET /api/status` setiap 2 detik untuk memperbarui kartu, progress bar, keyword aktif, ekor log, dan tombol;
  - **Ignore cooldown** → `prompt("Type YES to run anyway")`;
  - **Quit** → konfirmasi kalau API membalas 409, lalu tampilkan `quit.html`;
  - kalau polling gagal 3 kali, tampilkan banner `"Etsy Insights is not running. Open it again from Applications."`.
- Teks semua halaman mengikuti spec §3/§5 dan susunan mockup. Foto listing memakai `<img src="{{ card.image_url }}" alt="{{ card.title }}" loading="lazy">`.

- [ ] **Step 1: Tulis test yang gagal (`tests/test_web_pages.py`)**

```python
import re
import pytest
from etsy_insights.web import create_app
from etsy_insights.web.views import trend_points
from tests.web_helpers import TOKEN, FakeRunner, client, seeded_home

@pytest.fixture
def c(tmp_path):
    return client(create_app(seeded_home(tmp_path), token=TOKEN, runner=FakeRunner()))

def test_trend_points():
    assert trend_points([0, 100], width=100, height=110) == "0.0,110.0 100.0,10.0"
    assert trend_points([]) == ""

def test_session_page(c):
    html = c.get("/").get_data(as_text=True)
    assert f'content="{TOKEN}"' in html and "Start session" in html and "Test run (3 searches)" in html
    assert "Opportunities" in html and "My keywords" in html and "Peluang" not in html

def test_opportunities_filters_and_paging(c):
    html = c.get("/opportunities?label=Gold").get_data(as_text=True)
    labels = set(re.findall(r'data-label="(\w+)"', html))
    assert labels == {"Gold"} and "Download Excel" in html
    assert "custom address stamp" in c.get("/opportunities?q=address").get_data(as_text=True)
    page2 = c.get("/opportunities?label=Skip&page=2").get_data(as_text=True)
    assert 'aria-current="page">2<' in page2

def test_keyword_detail_searched_and_harvested(c):
    html = c.get("/keyword/sweatshirt").get_data(as_text=True)
    assert "Buyer taste" in html and "Popular themes" in html and "christmas" in html
    assert 'src="https://i.etsystatic.com/' in html and "Hard" in html and "<polyline" in html
    harvested = c.get("/keyword/gift%20for%20him").get_data(as_text=True)
    assert "Buyer taste appears after this keyword is searched" in harvested and "Prioritize" in harvested
    assert c.get("/keyword/nope-nope").status_code == 404

def test_keywords_and_settings_pages(c):
    html = c.get("/keywords").get_data(as_text=True)
    assert "Add keywords" in html and "Searched" in html and "No data" in html
    s = c.get("/settings").get_data(as_text=True)
    assert "Daily searches" in s and "1–30" in s and "Quit Etsy Insights" in s
```
Tambahkan juga ke `tests/test_taste.py`:
```python
def test_listing_card_image_url():
    assert build_profile(load_raw("sweatshirt")).examples[0].image_url.startswith("https://i.etsystatic.com/")
```
Dan ke `tests/test_store.py`:
```python
def test_harvested_from_sorted_by_volume():
    s = new_store("a")
    s.save_harvest(s.get("a").id, [make_related("x", 10), make_related("y", 500)], 200, 2, T0)
    assert [r.keyword for r in s.harvested_from(s.get("a").id)] == ["y", "x"]
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_pages.py tests/test_taste.py tests/test_store.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** view, template, CSS (warna dan jarak mengikuti mockup: latar `#F7F7F4`, aksen `#1F6F5C`, Inter/Space Grotesk dengan fallback system font tanpa ketergantungan internet), dan `app.js`.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Cek visual cepat:** jalankan server di port bebas dengan `seeded_home`, lalu screenshot `/`, `/opportunities`, `/keyword/sweatshirt` dengan Chromium (`deviceScaleFactor: 1`) ke scratchpad, dan bandingkan dengan mockup. Perbaiki kalau ada yang rusak.
- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: web pages for session, opportunities, keyword detail, keywords and settings"
```

---

### Task 7: Peluncur "Etsy Insights.app", README, dan paket

**Files:**
- Create: `macos/launcher.sh`, `macos/bootstrap.py`, `macos/Info.plist`, `tools/__init__.py`, `tools/build_app.py`, `tests/test_bootstrap.py`, `tests/test_build_app.py`, `macos/README.txt`
- Modify: `README.md`

**Interfaces:**
- **`macos/launcher.sh`** (menjadi `Contents/MacOS/etsy-insights`):
  - Cari Python ≥ 3.11 berurutan: `/Library/Frameworks/Python.framework/Versions/3.1[1-9]/bin/python3`, `/opt/homebrew/bin/python3`, `/usr/local/bin/python3`, `python3`.
  - Kalau tidak ada: `osascript` menampilkan dialog `"Etsy Insights needs Python 3.11 or newer."` dengan tombol `"Download Python"`/`"Cancel"`. Download membuka `https://www.python.org/downloads/macos/`, lalu `exit 1`.
  - Kalau `/Applications/Google Chrome.app` tidak ada: dialog `"Etsy Insights needs Google Chrome."` dengan tombol `"Download Chrome"` (membuka `https://www.google.com/chrome/`).
  - Lalu `exec "$PY" -I "$RES/bootstrap.py" "$@"`, dengan `$RES = Contents/Resources`.
- **`macos/bootstrap.py`** (stdlib saja):
  ```python
  APP_PORT_DEFAULT = 8765
  def app_home() -> Path                                   # ~/Library/Application Support/Etsy Insights
  def resources_layout(res: Path) -> tuple[Path, Path]       # (requirements.txt, app_dir): di bundle res/requirements.txt + res/app;
                                                            # dijalankan dari repo (macos/) -> res.parent/requirements.txt + res.parent
  def read_port(home: Path) -> int                          # baca `port_web = N` dari config.toml; default 8765
  def requirements_hash(path: Path) -> str                  # sha256 hex
  def ensure_venv(home: Path, python: str, requirements: Path, *, run=subprocess.run) -> Path
      # venv = home/"venv"; buat (python -m venv) + pip install -r bila home/".requirements-hash" != hash; tulis hash; return venv python
  def needs_import(home: Path) -> bool                      # tidak ada data/etsy.db dan tidak ada .import-asked
  def import_old_data(src: Path, home: Path) -> list[str]   # salin data/, keywords.txt, rekaman/ (yang ada); TIDAK config.toml
  def ping(port: int) -> str                                # "ours" | "other" | "none"
  def start_server(venv_python: Path, app_dir: Path, home: Path, port: int, *, popen=subprocess.Popen) -> None
      # [venv_python, "-m", "etsy_insights", "web", "--port", str(port)]; env ETSY_INSIGHTS_HOME, PYTHONPATH=app_dir;
      # stdout/stderr -> home/"server.log"; start_new_session=True
  def wait_for_server(port: int, timeout: float = 20, *, ping=ping, sleep=time.sleep) -> bool
  class MacDialogs: notify(msg); error(msg); ask_import() -> Path | None    # osascript
  def main(argv: list[str], *, dialogs=None, open_url=None, ping=ping, popen=subprocess.Popen,
           run=subprocess.run, python: str = sys.executable) -> int
  ```
  - **Alur `main`:**
    1. `home.mkdir`. Kalau `ping == "ours"`, langsung `open_url` lalu return 0.
    2. Kalau `"other"` → `dialogs.error("Port {p} is in use by another program. Change port_web in Settings, or quit the other program.")` lalu return 1.
    3. `ensure_venv` (dengan `notify` "Setting up Etsy Insights (one time, 1–2 minutes)…" kalau perlu memasang; kalau gagal → `error` berisi path log lalu return 1).
    4. Kalau `needs_import`: `ask_import`. Kalau dipilih → `import_old_data`. Tulis `.import-asked`.
    5. `start_server`, lalu `wait_for_server`. Kalau gagal → `error("Etsy Insights could not start. See …/server.log")` lalu return 1.
    6. `open_url(f"http://127.0.0.1:{port}/")` lalu return 0.
  - **`--cli ARGS…`:** `ensure_venv`, lalu jalankan `venv python -m etsy_insights ARGS` dengan env yang sama, dan return kode keluarnya. Ini cadangan Terminal.
- **`tools/build_app.py`:**
  ```python
  def make_icns(path: Path) -> None          # PNG 256 & 512 buatan stdlib (zlib/struct): kotak hijau #1F6F5C sudut bulat + 3 batang putih; chunk ic08/ic09
  def build_app(repo: Path, out_dir: Path, version: str) -> Path   # out_dir/"Etsy Insights.app"
  def make_zip(app: Path, readme: Path, out_zip: Path) -> Path      # simpan bit executable (external_attr)
  ```
  - Isi bundle:
    - `Contents/Info.plist` (dari `macos/Info.plist`, `CFBundleShortVersionString` = version);
    - `Contents/MacOS/etsy-insights` (mode 0755);
    - `Contents/Resources/bootstrap.py`, `requirements.txt`, `AppIcon.icns`;
    - `Contents/Resources/app/etsy_insights/**` (tanpa `__pycache__`), ditambah `config.toml` dan `keywords.txt` templat.
- **`macos/Info.plist`:** `CFBundleName`/`CFBundleDisplayName` = `Etsy Insights`, `CFBundleIdentifier` = `local.etsy-insights`, `CFBundleExecutable` = `etsy-insights`, `CFBundleIconFile` = `AppIcon`, `CFBundlePackageType` = `APPL`, `LSMinimumSystemVersion` = `11.0`.
- **README** (Indonesia):
  - pasang Python sekali;
  - seret app ke Applications;
  - klik kanan → Open saat pertama kali;
  - impor data lama;
  - pemakaian sehari-hari;
  - di mana data dan Excel disimpan;
  - Quit;
  - cadangan Terminal: `"/Applications/Etsy Insights.app/Contents/MacOS/etsy-insights" --cli run --uji`;
  - risiko akun.

  `macos/README.txt` adalah versi singkat yang ikut di dalam zip.

- [ ] **Step 1: Tulis test yang gagal**

```python
# tests/test_bootstrap.py
import importlib.util, sys
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).parent.parent / "macos" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)

class Dialogs:
    def __init__(self, choose=None): self.msgs, self.choose = [], choose
    def notify(self, m): self.msgs.append(("notify", m))
    def error(self, m): self.msgs.append(("error", m))
    def ask_import(self): return self.choose

def test_ensure_venv_runs_once_per_requirements(tmp_path):
    req = tmp_path / "requirements.txt"; req.write_text("flask\n")
    calls = []
    run = lambda args, **kw: calls.append(args) or type("R", (), {"returncode": 0})()
    bootstrap.ensure_venv(tmp_path, "python3", req, run=run)
    n = len(calls); bootstrap.ensure_venv(tmp_path, "python3", req, run=run)
    assert n >= 2 and len(calls) == n            # tidak diulang bila hash sama
    req.write_text("flask\nopenpyxl\n"); bootstrap.ensure_venv(tmp_path, "python3", req, run=run)
    assert len(calls) > n

def test_import_old_data_skips_config(tmp_path):
    old = tmp_path / "old"; (old / "data").mkdir(parents=True); (old / "rekaman").mkdir()
    (old / "data" / "etsy.db").write_bytes(b"db"); (old / "keywords.txt").write_text("mug\n")
    (old / "config.toml").write_text("kuota_harian = 50\n")
    home = tmp_path / "home"; home.mkdir()
    assert sorted(bootstrap.import_old_data(old, home)) == ["data", "keywords.txt", "rekaman"]
    assert (home / "data" / "etsy.db").read_bytes() == b"db" and not (home / "config.toml").exists()

def test_read_port(tmp_path):
    assert bootstrap.read_port(tmp_path) == 8765
    (tmp_path / "config.toml").write_text("port_web = 9001\n"); assert bootstrap.read_port(tmp_path) == 9001

def test_main_reuses_running_server(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "app_home", lambda: tmp_path)
    opened = []
    assert bootstrap.main([], dialogs=Dialogs(), open_url=opened.append, ping=lambda p: "ours") == 0
    assert opened == ["http://127.0.0.1:8765/"]

def test_main_reports_foreign_port(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "app_home", lambda: tmp_path)
    d = Dialogs()
    assert bootstrap.main([], dialogs=d, open_url=lambda u: None, ping=lambda p: "other") == 1
    assert d.msgs[0][0] == "error" and "8765" in d.msgs[0][1]

def test_main_first_launch_imports_and_starts(tmp_path, monkeypatch):
    home = tmp_path / "home"; monkeypatch.setattr(bootstrap, "app_home", lambda: home)
    old = tmp_path / "old"; (old / "data").mkdir(parents=True); (old / "data" / "etsy.db").write_bytes(b"db")
    states = iter(["none", "none", "ours"]); started, opened = [], []
    ok = type("R", (), {"returncode": 0})()
    rc = bootstrap.main([], dialogs=Dialogs(choose=old), open_url=opened.append, ping=lambda p: next(states),
                        popen=lambda args, **kw: started.append((args, kw)), run=lambda args, **kw: ok)
    assert rc == 0 and (home / "data" / "etsy.db").exists() and (home / ".import-asked").exists()
    args, kw = started[0]
    assert args[1:] == ["-m", "etsy_insights", "web", "--port", "8765"] and kw["env"]["ETSY_INSIGHTS_HOME"] == str(home)
    assert opened == ["http://127.0.0.1:8765/"]
```
```python
# tests/test_build_app.py
import plistlib, subprocess, zipfile
from pathlib import Path
from tools.build_app import build_app, make_zip

def test_build_app_bundle(tmp_path):
    app = build_app(Path("."), tmp_path, "3.0.0")
    c = app / "Contents"
    info = plistlib.loads((c / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "etsy-insights" and info["CFBundleName"] == "Etsy Insights"
    assert info["CFBundleShortVersionString"] == "3.0.0" and info["CFBundleIconFile"] == "AppIcon"
    exe = c / "MacOS" / "etsy-insights"
    assert exe.stat().st_mode & 0o111 and subprocess.run(["bash", "-n", str(exe)]).returncode == 0
    assert (c / "Resources" / "app" / "etsy_insights" / "__main__.py").exists()
    assert (c / "Resources" / "AppIcon.icns").read_bytes()[:4] == b"icns"
    assert not list((c / "Resources" / "app").rglob("__pycache__")) and not (c / "Resources" / "app" / "tests").exists()
    z = make_zip(app, Path("macos/README.txt"), tmp_path / "x.zip")
    info = zipfile.ZipFile(z).getinfo("Etsy Insights.app/Contents/MacOS/etsy-insights")
    assert (info.external_attr >> 16) & 0o111
```
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_bootstrap.py tests/test_build_app.py -q`. Expected: FAIL (file belum ada).
- [ ] **Step 3: Implementasi** `launcher.sh`, `bootstrap.py`, `Info.plist`, `build_app.py`, `README.txt`, dan README.
- [ ] **Step 4: Jalankan semua test + smoke.** Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`. Expected: semua PASS.
- [ ] **Step 5: Commit lalu buat paket**

```bash
git add -A && git commit -m "feat: Etsy Insights.app launcher, bootstrap, build script and README"
```

Run: `.venv/bin/python -m tools.build_app 3.0.0 && zipinfo dist/Etsy-Insights.zip | grep "MacOS/etsy-insights"`. Perintah ini membuat `dist/Etsy Insights.app` dan `dist/Etsy-Insights.zip`; `dist/` masuk `.gitignore`.
Expected: `-rwxr-xr-x`. Salin zip ke `/home/user/` untuk dikirim.
