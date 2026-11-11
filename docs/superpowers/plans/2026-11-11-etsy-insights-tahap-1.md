# Etsy Insights — Tahap 1 (Fondasi + Kenali) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paket yang bisa dijalankan pengguna di Mac: `setup.command` untuk
memasang, `kenali.command` untuk merekam data halaman Marketplace Insights,
dan `export.command` untuk membuat Excel. Di baliknya sudah ada fondasi
lengkap (config, database, ritme, sesi, skor, Excel) dan sudah dites. Yang
belum ada hanya pembaca halaman Etsy yang asli, yang dikerjakan di Tahap 2.

**Architecture:** Paket Python `etsy_insights` dengan unit kecil yang
dipisah menurut tanggung jawab. `session.py` hanya berinteraksi dengan
protokol `InsightsPage` dan fungsi `parse`, sehingga seluruh alur sesi bisa
dites dengan `FakePage`. Chrome asli diluncurkan sebagai proses biasa, lalu
disambung lewat `connect_over_cdp`.

**Tech Stack:** Python ≥ 3.11 (`tomllib`, `sqlite3`), `playwright`
(hanya `connect_over_cdp`), `openpyxl`, dan `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-11-etsy-insights-scraper-design.md`

**Di luar rencana ini (Tahap 2, rencana terpisah setelah rekaman kenali):**
`insights_page.py` (implementasi asli `InsightsPage` beserta deteksi bahaya),
`parser.py`, perintah CLI `run` (termasuk `--uji`, `--abaikan-pendinginan`
dengan konfirmasi `YA`, dan log ke `logs/`), serta `mulai.command`.

**Penyesuaian kecil dari spec (disengaja):**

- Kunci sensitif yang disensor ditambah `nonce` dan `nnc`. Etsy memakai
  `_nnc` untuk token CSRF.
- Ambang Emas memakai `≥ 200/3` (66,67), yaitu sepertiga teratas yang
  sebenarnya. Spec menulis 66,7, yang akan menolak persentil 66,67.
- Baris 1 setiap sheet Excel berisi baris info. Header ada di baris 2.

## Global Constraints

- Python ≥ 3.11. Dependensi runtime hanya `playwright>=1.48,<2` dan `openpyxl>=3.1,<4`. Dependensi dev: `pytest>=8`.
- Platform: macOS. Chrome di `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. Profil di `~/Library/Application Support/EtsyRiset/chrome-profile`. Port debug default `9222` di `127.0.0.1`.
- Playwright **tidak pernah meluncurkan Chrome sendiri** (tidak ada `--enable-automation`). Tidak ada proxy, penyamaran fingerprint, penembusan CAPTCHA, pemanggilan API internal Etsy secara langsung, atau tab paralel.
- Semua teks yang dilihat pengguna dalam Bahasa Indonesia.
- Batas keras: `kuota_harian ≤ 100`, `durasi_sesi_menit ≤ 60`, batas bawah `jeda_antar_keyword_detik ≥ 15`, batas bawah `kecepatan_ketik_ms ≥ 40`, batas bawah `waktu_baca_detik ≥ 3`, `kedalaman_maks ≤ 3`, `cek_ulang_setelah_hari ≥ 7`, `pendinginan_jam ≥ 12`.
- Data hanya lokal: `data/etsy.db`, `hasil/`, `logs/`, `rekaman/` (semuanya di `.gitignore`).
- Semua `datetime` timezone-aware dan disimpan di SQLite sebagai string ISO-8601 UTC. "Hari" berarti tanggal lokal.
- `conversion_rate` disimpan sebagai pecahan 0..1 (0,032 = 3,2%).
- Test dijalankan dengan `.venv/bin/pytest` dari root proyek.

## Review Focus

1. **`keywords.txt` berantakan** (BOM, CRLF, baris kosong, komentar `#`, duplikat beda huruf besar/kecil, spasi berlebih) harus menghasilkan daftar bersih tanpa duplikat. Dites di Task 2 `test_read_keywords_file_messy`.
2. **`config.toml` salah tulis** (TOML rusak atau tipe salah) tidak boleh menampilkan traceback. Yang muncul: pesan Indonesia dengan nomor baris, atau nilai default + peringatan. Dites di Task 1 (`test_invalid_toml_*`, `test_wrong_type_*`) dan Task 9 (`test_cli_bad_config_returns_1`).
3. **Daftar keyword terkait berisi keyword itu sendiri, induknya, duplikat, atau string kosong** tidak boleh membuat loop atau duplikat. Dites di Task 2 `test_add_related_skips_self_existing_blank`.
4. **Export saat database kosong atau tidak ada keyword layak** tetap harus menghasilkan Excel valid berisi header dan catatan. Dites di Task 5 `test_export_empty`.
5. **Ctrl+C saat jeda atau saat mengetik** tidak boleh meninggalkan keyword berstatus `in_progress`, dan baris sesi harus ditutup dengan alasan `dihentikan`. Dites di Task 6 `test_interrupt_during_sleep` dan `test_interrupt_during_search`.

---

### Task 1: Kerangka proyek, model bersama, config

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `config.toml`, `etsy_insights/__init__.py`, `etsy_insights/models.py`, `etsy_insights/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces (`models.py`, dipakai oleh semua task):
  ```python
  CompetitionKind = Literal["count", "level"]   # level: 1=Rendah, 2=Sedang, 3=Tinggi
  @dataclass(frozen=True)
  class KeywordMetrics:
      has_data: bool
      search_volume: int | None = None
      conversion_rate: float | None = None      # 0..1
      competition_value: float | None = None
      competition_kind: CompetitionKind | None = None
      trend: tuple[float, ...] = ()             # terlama -> terbaru
      related: tuple[str, ...] = ()
  @dataclass(frozen=True)
  class CapturedResponse: url: str; status: int; body: Any
  @dataclass(frozen=True)
  class RawResult: keyword: str; page_url: str; responses: tuple[CapturedResponse, ...]; html: str
  @dataclass(frozen=True)
  class DangerSignal: kind: Literal["captcha", "verifikasi", "login", "http_403", "http_429"]; detail: str
  @dataclass(frozen=True)
  class QueueItem: id: int; keyword: str; source: Literal["user", "related"]; depth: int; parent_keyword: str | None; status: str; fail_count: int; added_at: datetime
  @dataclass(frozen=True)
  class ResultRow: keyword_id: int; keyword: str; source: str; depth: int; parent_keyword: str | None; status: str; checked_at: datetime; metrics: KeywordMetrics
  class NotLoggedIn(Exception): ...
  class PageLoadTimeout(Exception): ...
  class BrowserClosed(Exception): ...
  class ParseError(Exception): ...
  class InsightsPage(Protocol):
      def open(self) -> None: ...                       # bisa raise NotLoggedIn
      def search(self, keyword: str) -> RawResult: ...  # bisa raise PageLoadTimeout, BrowserClosed
      def check_danger(self) -> DangerSignal | None: ...
      def dwell(self, seconds: float, scroll: bool) -> None: ...
  ```
- Produces (`config.py`): `Config` (frozen dataclass), `ConfigError(Exception)`, `load_config(path: Path) -> tuple[Config, list[str]]` (config + daftar peringatan).
  Field `Config` beserta default-nya: `kuota_harian=50`, `durasi_sesi_menit=45`, `jeda_antar_keyword_detik=(20, 60)`, `istirahat_setiap=(8, 12)`, `istirahat_detik=(120, 300)`, `kecepatan_ketik_ms=(60, 180)`, `waktu_baca_detik=(5, 15)`, `keyword_terkait_maks=10`, `kedalaman_maks=2`, `cek_ulang_setelah_hari=30`, `pendinginan_jam=24`, `volume_minimum=100`, `bobot=(0.40, 0.35, 0.25)` (urutan: volume, conversion, kompetisi), `port_debug=9222`.
  Di TOML, rentang ditulis sebagai array 2 angka. Bobot ditulis di tabel `[bobot]` dengan kunci `volume`, `conversion`, `kompetisi`.

- [ ] **Step 1: Buat kerangka**

`requirements.txt`: `playwright>=1.48,<2` dan `openpyxl>=3.1,<4`. `requirements-dev.txt`: `-r requirements.txt` dan `pytest>=8`. `pyproject.toml` hanya berisi `[tool.pytest.ini_options]` dengan `testpaths = ["tests"]`, `pythonpath = ["."]`, dan `markers = ["smoke: butuh Chromium asli"]`. `etsy_insights/__init__.py` berisi `__version__ = "0.1.0"`. `config.toml` memuat semua kunci dengan nilai default dan komentar Indonesia singkat per kunci, termasuk batas kerasnya. Lalu buat venv:

Run: `python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt`
Expected: selesai tanpa error.

- [ ] **Step 2: Tulis test yang gagal di `tests/test_config.py`**

```python
from pathlib import Path
import pytest
from etsy_insights.config import Config, ConfigError, load_config

def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"; p.write_text(text, encoding="utf-8"); return p

def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "tidak-ada.toml") == (Config(), [])

def test_shipped_config_equals_defaults():
    cfg, warnings = load_config(Path("config.toml"))
    assert cfg == Config() and warnings == []

def test_defaults_match_spec():
    c = Config()
    assert (c.kuota_harian, c.durasi_sesi_menit) == (50, 45)
    assert c.jeda_antar_keyword_detik == (20, 60) and c.istirahat_setiap == (8, 12)
    assert c.istirahat_detik == (120, 300) and c.kecepatan_ketik_ms == (60, 180)
    assert c.waktu_baca_detik == (5, 15) and c.keyword_terkait_maks == 10
    assert (c.kedalaman_maks, c.cek_ulang_setelah_hari, c.pendinginan_jam) == (2, 30, 24)
    assert c.volume_minimum == 100 and c.bobot == (0.40, 0.35, 0.25) and c.port_debug == 9222

def test_hard_caps_clamp_with_warning(tmp_path):
    cfg, warnings = load_config(write(tmp_path,
        "kuota_harian = 500\ndurasi_sesi_menit = 120\njeda_antar_keyword_detik = [5, 10]\n"
        "kecepatan_ketik_ms = [10, 50]\nwaktu_baca_detik = [1, 2]\nkedalaman_maks = 9\n"
        "cek_ulang_setelah_hari = 1\npendinginan_jam = 2\n"))
    assert (cfg.kuota_harian, cfg.durasi_sesi_menit) == (100, 60)
    assert cfg.jeda_antar_keyword_detik == (15, 15)
    assert cfg.kecepatan_ketik_ms == (40, 50) and cfg.waktu_baca_detik == (3, 3)
    assert (cfg.kedalaman_maks, cfg.cek_ulang_setelah_hari, cfg.pendinginan_jam) == (3, 7, 12)
    assert len(warnings) == 8

def test_reversed_range_is_sorted(tmp_path):
    cfg, warnings = load_config(write(tmp_path, "jeda_antar_keyword_detik = [60, 20]\n"))
    assert cfg.jeda_antar_keyword_detik == (20, 60)

def test_weights_normalized(tmp_path):
    cfg, _ = load_config(write(tmp_path, "[bobot]\nvolume = 2\nconversion = 1\nkompetisi = 1\n"))
    assert cfg.bobot == (0.5, 0.25, 0.25)

def test_all_zero_weights_fall_back_to_default(tmp_path):
    cfg, warnings = load_config(write(tmp_path, "[bobot]\nvolume = 0\nconversion = 0\nkompetisi = 0\n"))
    assert cfg.bobot == (0.40, 0.35, 0.25) and any("bobot" in w for w in warnings)

def test_invalid_toml_raises_config_error_with_line(tmp_path):
    with pytest.raises(ConfigError, match=r"config\.toml.*baris 1"):
        load_config(write(tmp_path, "kuota_harian = = 5\n"))

def test_wrong_type_uses_default_with_warning(tmp_path):
    cfg, warnings = load_config(write(tmp_path, 'kuota_harian = "lima puluh"\ndurasi_sesi_menit = -5\n'))
    assert (cfg.kuota_harian, cfg.durasi_sesi_menit) == (50, 45)
    assert any("kuota_harian" in w for w in warnings) and any("durasi_sesi_menit" in w for w in warnings)

def test_unknown_key_warns(tmp_path):
    cfg, warnings = load_config(write(tmp_path, "kuota = 10\n"))
    assert cfg == Config() and any("kuota" in w for w in warnings)
```

- [ ] **Step 3: Jalankan test, pastikan gagal**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: etsy_insights.config`).

- [ ] **Step 4: Implementasi `models.py` (persis seperti blok Interfaces) dan `config.py`**

`load_config`: file tidak ada → `(Config(), [])`. TOML rusak → `ConfigError` dengan pesan `"config.toml tidak valid di baris {lineno}: {msg}"`. Di Python 3.11–3.13, `tomllib.TOMLDecodeError` belum punya atribut `lineno`, jadi ambil angkanya dari teks error dengan regex `line (\d+)` (fallback `?`). Untuk setiap kunci:
- Bukan angka, atau angka negatif → pakai default + peringatan yang menyebut nama kunci.
- Rentang → urutkan dulu, naikkan batas bawah ke batas keras minimum, lalu `hi = max(hi, lo)`.
- Satu peringatan untuk setiap kunci yang dibatasi.
- Kunci yang tidak dikenal → peringatan.

`bool` tidak dianggap angka.

- [ ] **Step 5: Jalankan test, pastikan lulus**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: semua PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: project scaffold, shared models, config with hard caps"
```

---

### Task 2: Store (SQLite: antrean, hasil, sesi)

**Files:**
- Create: `etsy_insights/store.py`, `tests/helpers.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `KeywordMetrics`, `RawResult`, `QueueItem`, `ResultRow` (Task 1).
- Produces:
  ```python
  def normalize_keyword(text: str) -> str            # strip, lowercase, spasi ganda -> satu
  def read_keywords_file(path: Path) -> list[str]    # dinormalisasi, dedup, urutan tetap; file tidak ada -> []
  class Store:
      def __init__(self, path: str | Path) -> None   # ":memory:" didukung; buat folder induk + skema
      def close(self) -> None
      def sync_user_keywords(self, keywords: Iterable[str], now: datetime) -> int   # jumlah yang baru ditambah atau dinaikkan
      def add_related(self, parent_id: int, keywords: Iterable[str], max_count: int, max_depth: int, now: datetime) -> int
      def next_keyword(self, now: datetime, recheck_days: int, exclude_ids: Collection[int] = ()) -> QueueItem | None
      def get(self, keyword: str) -> QueueItem | None   # dinormalisasi dulu
      def mark_in_progress(self, keyword_id: int) -> None
      def return_to_pending(self, keyword_id: int) -> None
      def save_result(self, keyword_id: int, metrics: KeywordMetrics, raw: RawResult, now: datetime, parser_version: str) -> None
      def record_failure(self, keyword_id: int) -> str      # status baru: "pending" atau "failed" (fail_count >= 3)
      def recover_in_progress(self) -> int
      def start_session(self, now: datetime) -> int
      def increment_checked(self, session_id: int) -> None
      def end_session(self, session_id: int, now: datetime, stop_reason: str, cooldown_until: datetime | None) -> None
      def checked_on(self, day: date, tz: tzinfo) -> int    # jumlah checked_count sesi yang dimulai pada tanggal lokal itu
      def active_cooldown_until(self, now: datetime) -> datetime | None
      def latest_results(self) -> list[ResultRow]           # satu baris terbaru per keyword
      def all_results(self) -> list[ResultRow]              # semua hasil, checked_at menurun
      def pending_queue(self) -> list[QueueItem]            # hanya pending, urutan antrean
      def status_counts(self) -> dict[str, int]             # hanya status dengan jumlah > 0
      def last_session(self) -> dict | None                 # kunci: started_at, ended_at, checked_count, stop_reason, cooldown_until
  ```
- Produces (`tests/helpers.py`): `T0 = datetime(2026, 11, 11, 10, 0, tzinfo=timezone(timedelta(hours=7)))`, `make_metrics(volume=1000, cr=0.05, comp=100.0, kind="count", related=(), trend=(), has_data=True) -> KeywordMetrics`, `make_raw(keyword) -> RawResult` (tanpa respons, html `""`), `make_row(keyword, volume, cr, comp, kind="count", source="user", parent=None, has_data=True, trend=(), keyword_id=0) -> ResultRow` (status `"done"`, checked_at `T0`).

Skema mengikuti spec §7. `raw_json` adalah `json.dumps(dataclasses.asdict(raw))`. Kolom `trend_json` dan `related_json` berisi list JSON. `save_result` mengisi status `done` (atau `no_data` kalau `has_data` False), `last_checked_at = now`, dan `fail_count = 0`.

Urutan `next_keyword`: (1) `pending` + `user`, `added_at` naik; (2) `pending` + `related`, `depth` naik, lalu `added_at` naik; (3) hanya kalau tidak ada `pending` yang memenuhi syarat: `done`/`no_data` dengan `last_checked_at < now - recheck_days`, `last_checked_at` naik. `exclude_ids` berlaku untuk ketiganya. Nilai seri `added_at` dipecah dengan `id`.

- [ ] **Step 1: Tulis `tests/helpers.py` lalu test yang gagal di `tests/test_store.py`**

```python
from datetime import timedelta
from etsy_insights.store import Store, normalize_keyword, read_keywords_file
from tests.helpers import T0, make_metrics, make_raw

def new_store(*kws):
    s = Store(":memory:"); s.sync_user_keywords(kws, T0); return s

def test_normalize():
    assert normalize_keyword("  Boho   Wall ART ") == "boho wall art" and normalize_keyword("   ") == ""

def test_read_keywords_file_messy(tmp_path):
    p = tmp_path / "keywords.txt"
    p.write_bytes("﻿Boho Wall Art\r\n\r\n# komentar\r\nboho wall art\r\n  macrame  \r\n".encode())
    assert read_keywords_file(p) == ["boho wall art", "macrame"]
    assert read_keywords_file(tmp_path / "tidak-ada.txt") == []

def test_sync_adds_once():
    s = Store(":memory:")
    assert s.sync_user_keywords(["a", "b"], T0) == 2 and s.sync_user_keywords(["A"], T0) == 0

def test_sync_promotes_related_to_user():
    s = new_store("a"); s.add_related(s.get("a").id, ["b"], 10, 2, T0)
    assert s.sync_user_keywords(["b"], T0) == 1
    b = s.get("b"); assert (b.source, b.depth, b.parent_keyword) == ("user", 0, None)

def test_queue_order_user_first_then_by_depth():
    s = new_store("a", "b")
    s.add_related(s.get("a").id, ["a1"], 10, 2, T0 + timedelta(seconds=1))
    s.add_related(s.get("a1").id, ["a2"], 10, 2, T0 + timedelta(seconds=2))
    s.add_related(s.get("b").id, ["b1"], 10, 2, T0 + timedelta(seconds=3))
    assert [q.keyword for q in s.pending_queue()] == ["a", "b", "a1", "b1", "a2"]

def test_add_related_respects_max_count_and_depth():
    s = new_store("a")
    assert s.add_related(s.get("a").id, ["x", "y", "z"], 2, 2, T0) == 2
    s.add_related(s.get("x").id, ["x1"], 10, 2, T0)
    assert s.get("x1").depth == 2 and s.add_related(s.get("x1").id, ["x2"], 10, 2, T0) == 0

def test_add_related_skips_self_existing_blank():
    s = new_store("a", "b")
    assert s.add_related(s.get("a").id, ["A", " a ", "", "b", "new", "NEW"], 10, 2, T0) == 1
    assert s.get("new").parent_keyword == "a"

def test_next_keyword_excludes_ids():
    s = new_store("a", "b")
    assert s.next_keyword(T0, 30, exclude_ids={s.get("a").id}).keyword == "b"

def test_recheck_only_when_no_pending_and_old_enough():
    s = new_store("old", "recent", "p")
    s.save_result(s.get("old").id, make_metrics(), make_raw("old"), T0 - timedelta(days=31), "t")
    s.save_result(s.get("recent").id, make_metrics(), make_raw("recent"), T0 - timedelta(days=10), "t")
    assert s.next_keyword(T0, 30).keyword == "p"
    s.save_result(s.get("p").id, make_metrics(), make_raw("p"), T0, "t")
    assert s.next_keyword(T0, 30).keyword == "old"

def test_save_result_statuses():
    s = new_store("a", "b")
    s.save_result(s.get("a").id, make_metrics(), make_raw("a"), T0, "t")
    s.save_result(s.get("b").id, make_metrics(has_data=False), make_raw("b"), T0, "t")
    assert (s.get("a").status, s.get("b").status) == ("done", "no_data")

def test_three_failures_mark_failed():
    s = new_store("a"); kid = s.get("a").id
    assert [s.record_failure(kid) for _ in range(3)] == ["pending", "pending", "failed"]
    assert s.next_keyword(T0, 30) is None

def test_recover_in_progress():
    s = new_store("a"); s.mark_in_progress(s.get("a").id)
    assert s.recover_in_progress() == 1 and s.get("a").status == "pending"

def test_sessions_quota_and_cooldown():
    s = Store(":memory:"); sid = s.start_session(T0)
    for _ in range(3): s.increment_checked(sid)
    s.end_session(sid, T0, "tanda_bahaya", T0 + timedelta(hours=24))
    assert s.checked_on(T0.date(), T0.tzinfo) == 3
    assert s.checked_on((T0 + timedelta(days=1)).date(), T0.tzinfo) == 0
    assert s.active_cooldown_until(T0 + timedelta(hours=1)) == T0 + timedelta(hours=24)
    assert s.active_cooldown_until(T0 + timedelta(hours=25)) is None
    assert s.last_session()["stop_reason"] == "tanda_bahaya"

def test_latest_results_newest_per_keyword_with_parent():
    s = new_store("a"); s.add_related(s.get("a").id, ["b"], 10, 2, T0)
    s.save_result(s.get("b").id, make_metrics(volume=1), make_raw("b"), T0, "t")
    s.save_result(s.get("b").id, make_metrics(volume=2, related=("z",)), make_raw("b"), T0 + timedelta(days=40), "t")
    [row] = s.latest_results()
    assert (row.keyword, row.parent_keyword, row.metrics.search_volume, row.metrics.related) == ("b", "a", 2, ("z",))
    assert len(s.all_results()) == 2
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `.venv/bin/pytest tests/test_store.py -q`
Expected: FAIL (`ModuleNotFoundError: etsy_insights.store`).

- [ ] **Step 3: Implementasi `etsy_insights/store.py`** sesuai Interfaces dan aturan di atas. `datetime` dikembalikan dengan timezone UTC. Test membandingkan nilai `datetime` yang aware, jadi perbedaan timezone tidak masalah.

- [ ] **Step 4: Jalankan, pastikan lulus**

Run: `.venv/bin/pytest -q`
Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: SQLite store for keyword queue, results and sessions"
```

---

### Task 3: Pacer (ritme manusia, kuota, pendinginan)

**Files:**
- Create: `etsy_insights/pacer.py`, `tests/test_pacer.py`

**Interfaces:**
- Consumes: `Config` (Task 1).
- Produces:
  ```python
  HESITATION_CHANCE = 0.10; HESITATION_MS = (300, 900); SCROLL_CHANCE = 0.5
  class Pacer:
      def __init__(self, cfg: Config, rng: random.Random) -> None
      def typing_delay_ms(self) -> float   # uniform(kecepatan_ketik_ms) + (uniform(HESITATION_MS) jika rng.random() < HESITATION_CHANCE)
      def dwell_seconds(self) -> float     # uniform(waktu_baca_detik)
      def should_scroll(self) -> bool      # rng.random() < SCROLL_CHANCE
      def gap_seconds(self) -> float       # uniform(jeda_antar_keyword_detik)
      def break_every(self) -> int         # randint(istirahat_setiap)
      def break_seconds(self) -> float     # uniform(istirahat_detik)
  def remaining_quota(cfg: Config, checked_today: int, max_keywords: int | None = None) -> int
  def cooldown_end(now: datetime, cfg: Config) -> datetime
  ```

- [ ] **Step 1: Tulis test yang gagal**

```python
import random
from datetime import timedelta
from etsy_insights.config import Config
from etsy_insights.pacer import Pacer, cooldown_end, remaining_quota
from tests.helpers import T0

def test_ranges_and_chances():
    p = Pacer(Config(), random.Random(1))
    typing = [p.typing_delay_ms() for _ in range(2000)]
    assert all(60 <= t <= 1080 for t in typing)
    assert 0.06 <= sum(t > 180 for t in typing) / 2000 <= 0.14
    assert all(5 <= p.dwell_seconds() <= 15 for _ in range(500))
    assert all(20 <= p.gap_seconds() <= 60 for _ in range(500))
    assert all(120 <= p.break_seconds() <= 300 for _ in range(500))
    assert {p.break_every() for _ in range(500)} == {8, 9, 10, 11, 12}
    assert 0.45 <= sum(p.should_scroll() for _ in range(2000)) / 2000 <= 0.55

def test_same_seed_same_sequence():
    a, b = Pacer(Config(), random.Random(7)), Pacer(Config(), random.Random(7))
    assert [a.gap_seconds() for _ in range(5)] == [b.gap_seconds() for _ in range(5)]

def test_remaining_quota():
    c = Config()
    assert remaining_quota(c, 30) == 20 and remaining_quota(c, 70) == 0
    assert remaining_quota(c, 0, max_keywords=3) == 3 and remaining_quota(c, 49, max_keywords=3) == 1

def test_cooldown_end():
    assert cooldown_end(T0, Config()) == T0 + timedelta(hours=24)
    assert cooldown_end(T0, Config(pendinginan_jam=36)) == T0 + timedelta(hours=36)
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_pacer.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `etsy_insights/pacer.py`** sesuai Interfaces.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: human-like pacer with quota and cooldown helpers"
```

---

### Task 4: Skor peluang

**Files:**
- Create: `etsy_insights/score.py`, `tests/test_score.py`

**Interfaces:**
- Consumes: `ResultRow`, `KeywordMetrics` (Task 1), `Config.bobot`, `Config.volume_minimum`.
- Produces:
  ```python
  EMAS_THRESHOLD = 200 / 3; POTENSIAL_THRESHOLD = 60.0
  LEVEL_LABELS = {1: "Rendah", 2: "Sedang", 3: "Tinggi"}
  @dataclass(frozen=True)
  class ScoredKeyword:
      row: ResultRow; eligible: bool
      p_volume: float | None; p_conversion: float | None; p_low_competition: float | None
      score: float | None; label: str      # "Emas" | "Potensial" | "Lewati" | "Data kurang"
      searches_per_listing: float | None
  def percentile_ranks(values: Sequence[float]) -> list[float]
  def label_for(p_volume: float | None, p_conversion: float | None, p_low_competition: float | None, score: float) -> str
  def score_all(rows: Sequence[ResultRow], cfg: Config) -> list[ScoredKeyword]
  ```

Aturan yang tidak ditentukan oleh signature:
- `percentile_ranks`: rank 1-based dengan rank rata-rata untuk nilai seri, `p = 100*(r-1)/(n-1)`. Kalau `n == 1`, `p = 50.0`.
- Sebuah metrik dianggap **tersedia** kalau minimal satu baris (dengan `has_data`) memilikinya. Baris **layak** kalau `has_data`, `search_volume >= volume_minimum`, dan semua metrik yang tersedia ada.
- Bobot dinormalisasi ulang hanya atas metrik yang tersedia. `label_for` hanya memeriksa persentil yang tidak `None`.
- `searches_per_listing = volume / competition_value` hanya kalau kind `count` dan nilainya > 0.
- Urutan output: baris layak berdasarkan skor menurun (seri: keyword naik), lalu baris "Data kurang" berdasarkan keyword.

- [ ] **Step 1: Tulis test yang gagal**

```python
import pytest
from etsy_insights.config import Config
from etsy_insights.score import label_for, percentile_ranks, score_all
from tests.helpers import make_row

def test_percentile_ranks():
    assert percentile_ranks([10, 20, 20, 30]) == [0, 50, 50, 100]
    assert percentile_ranks([5]) == [50.0] and percentile_ranks([]) == []

def test_score_example_from_spec():
    rows = [make_row("a", 1000, 0.05, 100), make_row("b", 500, 0.03, 1000),
            make_row("c", 2000, 0.01, 5000), make_row("d", 50, 0.10, 1)]
    out = score_all(rows, Config())
    assert [s.row.keyword for s in out] == ["a", "c", "b", "d"]
    a, c, b, d = out
    assert a.score == pytest.approx(80) and c.score == pytest.approx(40) and b.score == pytest.approx(30)
    assert (a.label, c.label, b.label, d.label) == ("Potensial", "Lewati", "Lewati", "Data kurang")
    assert a.searches_per_listing == pytest.approx(10.0) and d.score is None and not d.eligible

def test_emas_when_top_third_everywhere():
    rows = [make_row("a", 1000, 0.05, 100), make_row("b", 500, 0.03, 1000),
            make_row("c", 2000, 0.01, 5000), make_row("e", 4000, 0.09, 10)]
    e = score_all(rows, Config())[0]
    assert e.row.keyword == "e" and e.label == "Emas" and e.score == pytest.approx(100)

def test_label_boundaries():
    assert label_for(200 / 3, 200 / 3, 200 / 3, 66.7) == "Emas"
    assert label_for(66.6, 100, 100, 90) == "Potensial"
    assert label_for(10, 10, 10, 60) == "Potensial" and label_for(10, 10, 10, 59.99) == "Lewati"

def test_competition_levels():
    rows = [make_row("x", 1000, 0.05, 1, kind="level"), make_row("y", 1000, 0.05, 2, kind="level"),
            make_row("z", 1000, 0.05, 3, kind="level")]
    by = {s.row.keyword: s for s in score_all(rows, Config())}
    assert (by["x"].p_low_competition, by["y"].p_low_competition, by["z"].p_low_competition) == (100, 50, 0)
    assert by["x"].searches_per_listing is None

def test_missing_metric_reweights():
    rows = [make_row("p", 1000, None, 10), make_row("q", 2000, None, 20)]
    by = {s.row.keyword: s for s in score_all(rows, Config())}
    assert by["p"].eligible and by["p"].p_conversion is None
    assert by["p"].score == pytest.approx(0.25 / 0.65 * 100) and by["q"].score == pytest.approx(0.40 / 0.65 * 100)

def test_no_data_rows_are_data_kurang():
    [s] = score_all([make_row("n", None, None, None, has_data=False)], Config())
    assert s.label == "Data kurang" and not s.eligible
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_score.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `etsy_insights/score.py`** sesuai Interfaces dan aturan di atas.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: percentile-based opportunity score and labels"
```

---

### Task 5: Export Excel

**Files:**
- Create: `etsy_insights/export.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `ScoredKeyword`, `LEVEL_LABELS` (Task 4), `ResultRow`, `QueueItem` (Task 1).
- Produces:
  ```python
  PELUANG_HEADERS = ["Keyword", "Volume pencarian", "Conversion rate", "Kompetisi", "Pencarian per listing",
                     "Skor", "Label", "Tren", "Asal keyword", "Tanggal cek"]
  SEMUA_HEADERS = ["Keyword", "Status", "Tanggal cek", "Volume pencarian", "Conversion rate", "Kompetisi",
                   "Jenis kompetisi", "Keyword terkait", "Label terbaru"]
  ANTREAN_HEADERS = ["Keyword", "Sumber", "Kedalaman", "Asal keyword", "Ditambahkan"]
  LABEL_FILLS = {"Emas": "FFD966", "Potensial": "C6EFCE", "Lewati": "D9D9D9"}
  def export_excel(scored: Sequence[ScoredKeyword], history: Sequence[ResultRow],
                   queue: Sequence[QueueItem], out_dir: Path, today: date) -> Path
  ```

Format file:
- File `out_dir / f"peluang-{today.isoformat()}.xlsx"`. Folder dibuat kalau belum ada, dan file hari yang sama ditimpa.
- Sheet urut: `Peluang`, `Semua data`, `Antrean`. Setiap sheet: baris 1 berisi info, baris 2 header, data mulai baris 3, `freeze_panes = "A3"`, dan autofilter di range header + data.
- Info Peluang: `f"Diperbarui {today}. {n} keyword layak dirank."`. Kalau `n < 10`, ditambah `" Data masih sedikit (< 10 keyword layak), peringkat masih kasar."`.
- Peluang hanya berisi baris layak, dengan urutan input.
  - Conversion rate memakai format `0.0%`.
  - Kompetisi berupa angka (kind count) atau `LEVEL_LABELS` (kind level).
  - Skor dibulatkan 1 desimal.
  - Hanya sel Label yang diberi warna `LABEL_FILLS`.
  - Tren: `f"{(last-first)/first:+.0%}"` kalau minimal ada 2 nilai dan `first > 0`, selain itu `""`.
  - Asal keyword: `"daftar Anda"` atau `f"terkait dari: {parent}"`.
  - Tanggal cek: tanggal lokal `YYYY-MM-DD`.
- Semua data: satu baris per hasil. Keyword terkait digabung dengan `", "`. Label terbaru diambil dari `scored` berdasarkan keyword.
- Antrean: Sumber berisi `"daftar Anda"` atau `"terkait"`. Asal keyword berisi keyword induk apa adanya, atau `""` kalau tidak ada. Ditambahkan berisi tanggal lokal `YYYY-MM-DD`.

- [ ] **Step 1: Tulis test yang gagal**

```python
from openpyxl import load_workbook
from etsy_insights.config import Config
from etsy_insights.export import ANTREAN_HEADERS, PELUANG_HEADERS, SEMUA_HEADERS, export_excel
from etsy_insights.score import score_all
from etsy_insights.store import Store
from tests.helpers import T0, make_row

def test_export_sheets_order_and_colors(tmp_path):
    rows = [make_row("a", 1000, 0.05, 100, trend=(100, 112)), make_row("b", 500, 0.03, 1000),
            make_row("c", 2000, 0.01, 5000, source="related", parent="a"),
            make_row("e", 4000, 0.09, 10), make_row("d", 50, 0.1, 1)]
    scored = score_all(rows, Config())
    path = export_excel(scored, rows, [], tmp_path / "hasil", T0.date())
    assert path.name == "peluang-2026-11-11.xlsx"
    wb = load_workbook(path)
    assert wb.sheetnames == ["Peluang", "Semua data", "Antrean"]
    ws = wb["Peluang"]
    assert [c.value for c in ws[2]] == PELUANG_HEADERS and ws.freeze_panes == "A3"
    assert "4 keyword layak" in ws["A1"].value and "Data masih sedikit" in ws["A1"].value
    assert [ws.cell(r, 1).value for r in range(3, 7)] == ["e", "a", "c", "b"]
    assert ws.cell(3, 7).value == "Emas" and ws.cell(3, 7).fill.fgColor.rgb.endswith("FFD966")
    assert ws.cell(4, 8).value == "+12%" and ws.cell(5, 9).value == "terkait dari: a"
    assert ws.cell(4, 3).number_format == "0.0%"
    semua = wb["Semua data"]
    assert [c.value for c in semua[2]] == SEMUA_HEADERS and semua.max_row == 2 + 5

def test_export_empty(tmp_path):
    path = export_excel([], [], [], tmp_path, T0.date())
    wb = load_workbook(path)
    assert "0 keyword layak" in wb["Peluang"]["A1"].value
    assert [c.value for c in wb["Antrean"][2]] == ANTREAN_HEADERS

def test_export_queue_sheet(tmp_path):
    s = Store(":memory:"); s.sync_user_keywords(["a"], T0); s.add_related(s.get("a").id, ["b"], 10, 2, T0)
    ws = load_workbook(export_excel([], [], s.pending_queue(), tmp_path, T0.date()))["Antrean"]
    assert [ws.cell(3, c).value for c in (1, 2, 3)] == ["a", "daftar Anda", 0]
    assert [ws.cell(4, c).value for c in (1, 2, 4)] == ["b", "terkait", "a"]
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_export.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `etsy_insights/export.py`** dengan openpyxl sesuai format di atas.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Excel export with Peluang, Semua data and Antrean sheets"
```

---

### Task 6: Alur sesi (dites dengan FakePage)

**Files:**
- Create: `etsy_insights/session.py`, `tests/test_session.py`
- Modify: `tests/helpers.py` (tambah `FakeClock`, `FakePage`, `fake_parse`, `make_deps`)

**Interfaces:**
- Consumes: `Store` (Task 2), `Pacer`, `remaining_quota`, `cooldown_end` (Task 3), `InsightsPage`, `RawResult`, `KeywordMetrics`, exception-exception, `DangerSignal` (Task 1), `Config`.
- Produces:
  ```python
  class StopReason(str, Enum):
      QUOTA = "kuota_tercapai"; DURATION = "durasi_habis"; DANGER = "tanda_bahaya"
      FAILURES = "gagal_beruntun"; INTERRUPTED = "dihentikan"; BROWSER_CLOSED = "chrome_ditutup"
      QUEUE_EMPTY = "antrean_kosong"; NOT_LOGGED_IN = "belum_login"
      COOLDOWN = "masa_pendinginan"; NO_QUOTA = "kuota_habis"
  @dataclass
  class SessionDeps:
      store: Store; page: InsightsPage; parse: Callable[[RawResult], KeywordMetrics]
      pacer: Pacer; cfg: Config; clock: Callable[[], datetime]; sleep: Callable[[float], None]
      log: Callable[[str], None]; parser_version: str
  @dataclass(frozen=True)
  class SessionSummary:
      stop_reason: StopReason; checked: int; succeeded: int; no_data: int; failed: int
      new_keywords: int; queue_left: int; quota_left: int
      cooldown_until: datetime | None; danger: DangerSignal | None
  def run_session(deps: SessionDeps, max_keywords: int | None = None, ignore_cooldown: bool = False) -> SessionSummary
  def format_summary(summary: SessionSummary) -> str
  ```
- Produces (`tests/helpers.py`):
  - `FakeClock(start, interrupt_on_sleep: int | None = None)` dengan `.now()`, `.advance(s)`, `.sleep(s)` (mencatat ke `.sleeps` dan memajukan waktu; melempar `KeyboardInterrupt` pada pemanggilan sleep ke-n), dan `.sleeps: list[float]`.
  - `FakePage(clock, outcomes: dict[str, str] = {}, related: dict[str, tuple[str, ...]] = {}, danger_on_open: DangerSignal | None = None, open_error: Exception | None = None)` dengan `.opened`, `.searched`, `.dwells`. `dwell` memajukan clock.
    - Outcome `"ok"` (default), `"no_data"`, dan `"parse_error"` dikembalikan di `body`.
    - `"timeout"` melempar `PageLoadTimeout`, `"closed"` melempar `BrowserClosed`, `"interrupt"` melempar `KeyboardInterrupt`.
    - `"captcha"` dan `"403"` mengembalikan hasil normal, tetapi `check_danger()` berikutnya mengembalikan `DangerSignal("captcha", …)` / `DangerSignal("http_403", …)`.
  - `fake_parse(raw)` membaca `raw.responses[0].body`: `parse_error` melempar `ParseError`, `no_data` mengembalikan `KeywordMetrics(has_data=False)`, selain itu `make_metrics(related=body["related"])`.
  - `make_deps(store, page, clock, cfg=Config(), seed=1) -> SessionDeps` dengan `log` no-op dan `parser_version="test"`.

**Algoritma `run_session` (urutan ini yang dikunci oleh test):**

```
now = clock(); store.recover_in_progress()
if not ignore_cooldown and (cd := store.active_cooldown_until(now)): return summary(COOLDOWN, cooldown_until=cd)
limit = remaining_quota(cfg, store.checked_on(now.date(), now.tzinfo), max_keywords)
if limit == 0: return summary(NO_QUOTA)
sid = store.start_session(now); start = now; tried = set(); streak = 0; since_break = 0; next_break = pacer.break_every()
try:
    page.open()                                    # NotLoggedIn -> stop NOT_LOGGED_IN
    if danger := page.check_danger(): stop DANGER (cooldown_until = cooldown_end(clock(), cfg))
    loop:
        if checked >= limit: stop QUOTA
        if clock() - start >= durasi: stop DURATION
        item = store.next_keyword(clock(), cfg.cek_ulang_setelah_hari, tried); if None: stop QUEUE_EMPTY
        if checked > 0:
            if since_break >= next_break: sleep(pacer.break_seconds()); since_break = 0; next_break = pacer.break_every()
            else: sleep(pacer.gap_seconds())
            if clock() - start >= durasi: stop DURATION
        tried.add(item.id); store.mark_in_progress(item.id); store.increment_checked(sid); checked += 1; since_break += 1
        raw = page.search(item.keyword)             # PageLoadTimeout -> record_failure, streak += 1, lanjut ke cek streak
                                                    # BrowserClosed -> return_to_pending, stop BROWSER_CLOSED
        if danger := page.check_danger(): return_to_pending; stop DANGER (+ cooldown)
        metrics = parse(raw)                        # ParseError -> record_failure, streak += 1
        else: save_result; streak = 0; new += store.add_related(item.id, metrics.related, keyword_terkait_maks, kedalaman_maks, clock())
        if streak >= 3: stop FAILURES
        page.dwell(pacer.dwell_seconds(), pacer.should_scroll())   # hanya setelah pencarian yang berhasil di-parse
except KeyboardInterrupt: item yang sedang in_progress -> return_to_pending; stop INTERRUPTED
finally: store.end_session(sid, clock(), reason.value, cooldown_until)
```

`quota_left` di summary = `remaining_quota(cfg, checked_on(hari ini))` dihitung ulang di akhir, tanpa `max_keywords`. `queue_left = len(store.pending_queue())`.

`format_summary` menghasilkan beberapa baris Indonesia, termasuk persis `Keyword dicek: {checked}` dan `Sisa kuota hari ini: {quota_left}`. Kalau ada cooldown, ditambah `Masa pendinginan sampai: {waktu lokal}`. Alasan berhenti diambil dari dict `REASON_TEXT` (satu kalimat Indonesia per `StopReason`).

- [ ] **Step 1: Tambah fake ke `tests/helpers.py`, lalu tulis test yang gagal**

```python
from datetime import timedelta
from etsy_insights.config import Config
from etsy_insights.models import DangerSignal, NotLoggedIn
from etsy_insights.session import StopReason, format_summary, run_session
from etsy_insights.store import Store
from tests.helpers import T0, FakeClock, FakePage, make_deps

def setup(*kws, **page_kw):
    clock = FakeClock(T0, interrupt_on_sleep=page_kw.pop("interrupt_on_sleep", None))
    store = Store(":memory:"); store.sync_user_keywords(kws, T0)
    return clock, store, FakePage(clock, **page_kw)

def test_stops_at_max_keywords_without_trailing_sleep():
    clock, store, page = setup("a", "b", "c", "d", "e")
    s = run_session(make_deps(store, page, clock, Config(jeda_antar_keyword_detik=(20, 20))), max_keywords=3)
    assert (s.stop_reason, s.checked, s.succeeded) == (StopReason.QUOTA, 3, 3)
    assert page.searched == ["a", "b", "c"] and clock.sleeps == [20, 20] and len(page.dwells) == 3
    assert store.status_counts() == {"done": 3, "pending": 2}

def test_related_keywords_follow_user_keywords():
    clock, store, page = setup("a", "b", related={"a": ("a1", "a2")})
    s = run_session(make_deps(store, page, clock), max_keywords=4)
    assert page.searched == ["a", "b", "a1", "a2"] and s.new_keywords == 2

def test_queue_empty():
    clock, store, page = setup("a")
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, clock.sleeps) == (StopReason.QUEUE_EMPTY, 1, [])

def test_captcha_sets_cooldown_and_blocks_next_run():
    clock, store, page = setup("a", "b", "c", outcomes={"b": "captcha"})
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.DANGER and s.danger.kind == "captcha"
    assert s.cooldown_until == clock.now() + timedelta(hours=24)
    assert (store.get("b").status, store.get("b").fail_count) == ("pending", 0)
    page2 = FakePage(clock)
    assert run_session(make_deps(store, page2, clock)).stop_reason is StopReason.COOLDOWN and page2.opened == 0
    assert run_session(make_deps(store, page2, clock), ignore_cooldown=True).stop_reason is not StopReason.COOLDOWN

def test_danger_right_after_open():
    clock, store, page = setup("a", danger_on_open=DangerSignal("login", "/signin"))
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked) == (StopReason.DANGER, 0) and s.cooldown_until is not None

def test_three_consecutive_failures_stop_without_cooldown():
    clock, store, page = setup("a", "b", "c", "d", outcomes={"a": "parse_error", "b": "timeout", "c": "parse_error"})
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.failed, s.cooldown_until) == (StopReason.FAILURES, 3, None)
    assert page.searched == ["a", "b", "c"]
    assert [store.get(k).fail_count for k in "abc"] == [1, 1, 1] and store.get("a").status == "pending"

def test_success_resets_failure_streak():
    clock, store, page = setup(*"abcdef", outcomes={k: "parse_error" for k in "abde"})
    s = run_session(make_deps(store, page, clock), max_keywords=6)
    assert (s.stop_reason, s.failed, s.succeeded) == (StopReason.QUOTA, 4, 2)

def test_no_data_is_not_a_failure():
    clock, store, page = setup("a", outcomes={"a": "no_data"})
    s = run_session(make_deps(store, page, clock))
    assert (s.no_data, s.failed, store.get("a").status) == (1, 0, "no_data")

def test_browser_closed():
    clock, store, page = setup("a", "b", "c", outcomes={"b": "closed"})
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked) == (StopReason.BROWSER_CLOSED, 2)
    assert (store.get("b").status, store.get("b").fail_count) == ("pending", 0)

def test_interrupt_during_sleep():
    clock, store, page = setup("a", "b", interrupt_on_sleep=1)
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked) == (StopReason.INTERRUPTED, 1)
    assert store.status_counts() == {"done": 1, "pending": 1}
    assert store.last_session()["stop_reason"] == "dihentikan"

def test_interrupt_during_search():
    clock, store, page = setup("a", outcomes={"a": "interrupt"})
    s = run_session(make_deps(store, page, clock))
    assert s.stop_reason is StopReason.INTERRUPTED and store.status_counts() == {"pending": 1}

def test_not_logged_in():
    clock, store, page = setup("a", open_error=NotLoggedIn())
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, s.cooldown_until) == (StopReason.NOT_LOGGED_IN, 0, None)

def test_quota_used_up_and_partially_used():
    clock, store, page = setup("a", "b", "c")
    sid = store.start_session(T0)
    for _ in range(48): store.increment_checked(sid)
    store.end_session(sid, T0, "kuota_tercapai", None)
    s = run_session(make_deps(store, page, clock))
    assert (s.stop_reason, s.checked, s.quota_left) == (StopReason.QUOTA, 2, 0)
    page2 = FakePage(clock)
    s2 = run_session(make_deps(store, page2, clock))
    assert s2.stop_reason is StopReason.NO_QUOTA and page2.opened == 0

def test_duration_limit():
    clock, store, page = setup(*"abcde")
    cfg = Config(jeda_antar_keyword_detik=(900, 900), waktu_baca_detik=(5, 5))
    s = run_session(make_deps(store, page, clock, cfg))
    assert (s.stop_reason, s.checked, clock.sleeps) == (StopReason.DURATION, 3, [900, 900, 900])

def test_long_break_schedule():
    clock, store, page = setup(*"abcd")
    cfg = Config(jeda_antar_keyword_detik=(20, 20), istirahat_setiap=(2, 2), istirahat_detik=(200, 200))
    run_session(make_deps(store, page, clock, cfg))
    assert clock.sleeps == [20, 200, 20]

def test_format_summary():
    clock, store, page = setup("a", "b", "c", outcomes={"c": "captcha"})
    text = format_summary(run_session(make_deps(store, page, clock)))
    assert "Keyword dicek: 3" in text and "Sisa kuota hari ini: 47" in text and "Masa pendinginan sampai" in text
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_session.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `etsy_insights/session.py`** mengikuti algoritma di atas. Kejadian penting (mulai, keyword, berhenti) dilaporkan lewat `deps.log`.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: session loop with stop conditions, breaks and cooldown"
```

---

### Task 7: Sambungan ke Chrome

**Files:**
- Create: `etsy_insights/browser.py`, `tests/test_browser.py`, `tests/test_browser_smoke.py`

**Interfaces:**
- Produces:
  ```python
  CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
  PROFILE_DIR = Path.home() / "Library/Application Support/EtsyRiset/chrome-profile"
  class ChromeNotFound(Exception): ...
  class PortBusy(Exception): ...
  class ChromeStartTimeout(Exception): ...
  def chrome_args(chrome_path: Path, port: int, profile_dir: Path, extra_args: Sequence[str] = ()) -> list[str]
  def probe_debug_port(port: int, timeout: float = 1.0) -> dict | None   # GET http://127.0.0.1:{port}/json/version
  def port_in_use(port: int) -> bool
  def ensure_chrome(port: int, profile_dir: Path = PROFILE_DIR, chrome_path: Path = CHROME_PATH,
                    extra_args: Sequence[str] = (), *, launch=subprocess.Popen, probe=probe_debug_port,
                    in_use=port_in_use, sleep=time.sleep, wait_seconds: float = 15.0) -> str
  @contextmanager
  def connected_browser(endpoint: str) -> Iterator[BrowserContext]   # yield browser.contexts[0]
  ```

Aturan:
- `chrome_args` = `[str(chrome_path), f"--user-data-dir={profile_dir}", f"--remote-debugging-port={port}", "--no-first-run", "--no-default-browser-check", *extra_args]`.
- Alur `ensure_chrome`:
  1. `probe` mengembalikan info dengan `"Chrome"` di `info["Browser"]` → langsung kembalikan `f"http://127.0.0.1:{port}"`.
  2. Kalau tidak, dan `in_use(port)` → `PortBusy`.
  3. `chrome_path` tidak ada → `ChromeNotFound`.
  4. Buat `profile_dir`, lalu `launch(args, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)`. Probe setiap 0,5 detik sampai `wait_seconds` habis, kalau tetap gagal → `ChromeStartTimeout`.
  5. Pesan error dalam Bahasa Indonesia dan menyebut langkah perbaikan.
- `connected_browser` **tidak** menutup browser: saat keluar hanya memanggil `playwright.stop()`, sehingga Chrome tetap terbuka.

- [ ] **Step 1: Tulis test yang gagal di `tests/test_browser.py`**

```python
import pytest
from etsy_insights.browser import ChromeNotFound, ChromeStartTimeout, PortBusy, chrome_args, ensure_chrome

INFO = {"Browser": "Chrome/140.0.0.0"}

def fake_chrome(tmp_path):
    p = tmp_path / "chrome"; p.write_text(""); return p

def test_chrome_args(tmp_path):
    args = chrome_args(tmp_path / "c", 9222, tmp_path / "prof")
    assert args[0] == str(tmp_path / "c") and f"--user-data-dir={tmp_path / 'prof'}" in args
    assert "--remote-debugging-port=9222" in args and "--no-first-run" in args
    assert not any("automation" in a for a in args)

def test_reuses_running_chrome(tmp_path):
    launched = []
    ep = ensure_chrome(9222, tmp_path / "p", fake_chrome(tmp_path), launch=lambda *a, **k: launched.append(a),
                       probe=lambda port: INFO, in_use=lambda port: True, sleep=lambda s: None)
    assert ep == "http://127.0.0.1:9222" and launched == []

def test_launches_and_waits(tmp_path):
    launched, answers = [], iter([None, None, None, INFO])
    ep = ensure_chrome(9333, tmp_path / "p", fake_chrome(tmp_path), launch=lambda args, **k: launched.append(args),
                       probe=lambda port: next(answers), in_use=lambda port: False, sleep=lambda s: None)
    assert ep == "http://127.0.0.1:9333" and len(launched) == 1 and (tmp_path / "p").is_dir()

def test_timeout(tmp_path):
    with pytest.raises(ChromeStartTimeout):
        ensure_chrome(9222, tmp_path / "p", fake_chrome(tmp_path), launch=lambda *a, **k: None,
                      probe=lambda port: None, in_use=lambda port: False, sleep=lambda s: None, wait_seconds=2)

def test_port_busy(tmp_path):
    with pytest.raises(PortBusy, match="port_debug"):
        ensure_chrome(9222, tmp_path / "p", fake_chrome(tmp_path), probe=lambda port: None, in_use=lambda port: True)

def test_chrome_missing(tmp_path):
    with pytest.raises(ChromeNotFound):
        ensure_chrome(9222, tmp_path / "p", tmp_path / "tidak-ada", probe=lambda port: None, in_use=lambda port: False)
```

`tests/test_browser_smoke.py` (`@pytest.mark.smoke`, di-skip kalau env `CHROME_SMOKE_PATH` tidak ada): `ensure_chrome(9339, tmp_path/"prof", Path(os.environ["CHROME_SMOKE_PATH"]), ["--headless=new", "--no-sandbox"])` → dalam `connected_browser(ep)` buka `context.new_page()`, `goto("data:text/html,<title>ok</title>")`, lalu assert `page.title() == "ok"`. Setelah keluar dari context manager, assert `probe_debug_port(9339)` masih mengembalikan info (Chrome tetap hidup). Terakhir, matikan Chrome lewat proses yang ditemukan dengan `pkill -f remote-debugging-port=9339`.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_browser.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `etsy_insights/browser.py`** sesuai aturan di atas.
- [ ] **Step 4: Jalankan unit test + smoke dengan Chromium di container**

Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`
Expected: semua PASS, smoke 1 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: launch real Chrome with dedicated profile and attach over CDP"
```

---

### Task 8: Perekam mode kenal-halaman

**Files:**
- Create: `etsy_insights/recorder.py`, `tests/test_recorder.py`

**Interfaces:**
- Consumes: `BrowserContext` dari `connected_browser` (Task 7).
- Produces:
  ```python
  SENSITIVE_KEYS = ("csrf", "token", "email", "session", "cookie", "password", "secret",
                    "auth", "phone", "address", "nonce", "nnc")
  REDACTED = "[DIHAPUS]"; MAX_BODY_CHARS = 2_000_000; FORMAT = "etsy-insights-kenali/1"
  INSIGHTS_URL = "https://www.etsy.com/your/shops/me/marketplace-insights"
  def redact(value: Any) -> Any            # rekursif: nilai dari kunci dict yang mengandung SENSITIVE_KEYS (case-insensitive) -> REDACTED
  def redact_html(text: str) -> str        # email; pasangan "kunci":"nilai" bergaya JSON; atribut value=/content= pada tag yang name/id-nya sensitif
  @dataclass
  class Recording:
      started_at: datetime
      responses: list[dict] = field(default_factory=list)   # {"t", "url", "status", "content_type", "body"}
      snapshots: list[dict] = field(default_factory=list)   # {"t", "page_url", "html", "screenshot_png_base64"}
      def add_response(self, url: str, status: int, content_type: str, body_text: str, at: datetime) -> bool
      def add_snapshot(self, page_url: str, html: str, png: bytes, at: datetime) -> None   # html -> redact_html
      def to_dict(self) -> dict            # {"format": FORMAT, "started_at", "responses", "snapshots"}
      def save(self, out_dir: Path) -> Path   # out_dir / f"kenali-{started_at:%Y%m%d-%H%M}.json", UTF-8, indent=1
  def wait_for_line(page, stdin) -> str    # loop: page.wait_for_timeout(250); select.select([stdin], [], [], 0) -> readline().strip()
  def run_kenali(context, out_dir: Path, clock: Callable[[], datetime], stdin=sys.stdin, print_fn=print) -> Path
  ```

Aturan `add_response`:
- Hanya disimpan kalau host-nya `etsy.com` atau `*.etsy.com` **dan** `"json"` ada di content_type.
- Body lebih dari `MAX_BODY_CHARS` dipotong dan disimpan sebagai string `+ "...[TERPOTONG]"`.
- Body yang bisa di-parse sebagai JSON disimpan dalam bentuk `redact(obj)`. Selain itu disimpan sebagai `redact_html(text)`.

Alur `run_kenali` (I/O tipis, tanpa unit test; diuji manual oleh pengguna):
1. Daftarkan `context.on("response", …)`. Handler memakai filter murah dulu, lalu `response.text()` di dalam try/except.
2. `page = context.new_page(); page.goto(INSIGHTS_URL, wait_until="domcontentloaded")`.
3. Kalau `"signin"` ada di `page.url`, minta login di jendela Chrome lalu tunggu Enter lewat `wait_for_line`.
4. Ulangi: minta pengguna mencari keyword lalu menekan Enter. Ambil snapshot `content()` + `screenshot(full_page=True)` dari setiap tab di context yang URL-nya mengandung `etsy.com`. Tampilkan jumlah respons dan snapshot yang terekam. Kalau pengguna mengetik `selesai`: simpan file, tampilkan path-nya, dan minta file itu dikirim ke Claude.
5. Tab dan Chrome dibiarkan terbuka.

- [ ] **Step 1: Tulis test yang gagal**

```python
import base64, json
from etsy_insights.recorder import MAX_BODY_CHARS, REDACTED, Recording, redact, redact_html
from tests.helpers import T0

def test_redact_nested():
    out = redact({"user": {"email": "a@b.com", "name": "Toko"}, "csrf_nonce": "abc",
                  "items": [{"auth_token": "t", "q": "boho"}], "Session_ID": 5, "_nnc": "n"})
    assert out == {"user": {"email": REDACTED, "name": "Toko"}, "csrf_nonce": REDACTED,
                   "items": [{"auth_token": REDACTED, "q": "boho"}], "Session_ID": REDACTED, "_nnc": REDACTED}

def test_redact_html():
    html = ('<meta name="csrf_nonce" content="abc123"><input type="hidden" name="_nnc" value="v9">'
            '<p>hubungi saya@toko.com</p><script>{"api_token":"zzz","keyword":"boho"}</script>'
            '<input name="search_query" value="boho">')
    out = redact_html(html)
    for secret in ("abc123", "v9", "saya@toko.com", "zzz"): assert secret not in out
    assert '"keyword":"boho"' in out and 'name="search_query" value="boho"' in out

def test_add_response_filters():
    r = Recording(T0)
    assert r.add_response("https://www.etsy.com/api/v3/ajax/x", 200, "application/json", '{"q":"boho","csrf":"1"}', T0)
    assert r.add_response("https://api.etsy.com/v3/y", 200, "application/json; charset=utf-8", "[1]", T0)
    assert not r.add_response("https://notetsy.com/a", 200, "application/json", "{}", T0)
    assert not r.add_response("https://www.etsy.com/page", 200, "text/html", "<html>", T0)
    assert not r.add_response("https://www.google-analytics.com/c", 200, "application/json", "{}", T0)
    assert r.responses[0]["body"] == {"q": "boho", "csrf": REDACTED} and len(r.responses) == 2

def test_large_body_truncated():
    r = Recording(T0); r.add_response("https://www.etsy.com/x", 200, "application/json", "[" + "1," * MAX_BODY_CHARS + "1]", T0)
    body = r.responses[0]["body"]
    assert isinstance(body, str) and body.endswith("...[TERPOTONG]") and len(body) <= MAX_BODY_CHARS + 20

def test_save_roundtrip(tmp_path):
    r = Recording(T0); r.add_snapshot("https://www.etsy.com/your/shops/me/marketplace-insights", "<p>a@b.co</p>", b"\x89PNG", T0)
    path = r.save(tmp_path)
    assert path.name == "kenali-20261111-1000.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "etsy-insights-kenali/1" and "a@b.co" not in data["snapshots"][0]["html"]
    assert base64.b64decode(data["snapshots"][0]["screenshot_png_base64"]) == b"\x89PNG"
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_recorder.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `etsy_insights/recorder.py`** sesuai Interfaces dan aturan di atas.
- [ ] **Step 4: Jalankan, pastikan lulus.** Run: `.venv/bin/pytest -q`. Expected: semua PASS.
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: kenali recorder with redaction of sensitive values"
```

---

### Task 9: CLI, skrip `.command`, README, dan paket kiriman

**Files:**
- Create: `etsy_insights/__main__.py`, `setup.command`, `kenali.command`, `export.command`, `keywords.txt`, `README.md`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`/`ConfigError` (T1), `Store`/`read_keywords_file` (T2), `remaining_quota` (T3), `score_all` (T4), `export_excel` (T5), `ensure_chrome`/`connected_browser` + error-errornya (T7), `run_kenali` (T8).
- Produces: `main(argv: list[str] | None = None, *, base_dir: Path | None = None, now: Callable[[], datetime] | None = None) -> int`.
  - `base_dir` default = root proyek (`Path(__file__).resolve().parent.parent`). `now` default = `lambda: datetime.now().astimezone()`.
  - Path yang dipakai: `config.toml`, `keywords.txt`, `data/etsy.db`, `hasil/`, `rekaman/` di bawah `base_dir`.

Subcommand (argparse, `prog="etsy_insights"`):
- `status`: tampilkan peringatan config, sinkronkan `keywords.txt`, lalu cetak `Antrean: {n} menunggu`, `Hari ini: {x}/{kuota} keyword dicek`, `Masa pendinginan sampai: …` (kalau aktif), dan `Sesi terakhir: …` (kalau ada). Return 0.
- `export`: sinkronkan keywords, lalu `export_excel(score_all(latest_results), all_results, pending_queue, base/"hasil", now().date())`. Cetak `File Excel: {path}`. Return 0.
- `kenali`: `ensure_chrome(cfg.port_debug)`, lalu `connected_browser`, lalu `run_kenali(context, base/"rekaman", now)`. Return 0.
- `ConfigError`, `ChromeNotFound`, `PortBusy`, `ChromeStartTimeout` → cetak pesannya (tanpa traceback), return 1.

Skrip `.command` (bash, executable, `cd "$(dirname "$0")"` di awal, ditutup `read -r -p "Tekan Enter untuk menutup..."`):
- `setup.command`: cari Python ≥ 3.11 berurutan dari `python3.13`, `python3.12`, `python3.11`, `python3`. Kalau tidak ada, tampilkan link `https://www.python.org/downloads/macos/` lalu keluar 1. Buat `.venv` dan `pip install -r requirements.txt`. Beri peringatan kalau Chrome tidak ada di `/Applications`. `mkdir -p data hasil logs rekaman`.
- `kenali.command` / `export.command`: kalau `.venv` tidak ada, minta pengguna menjalankan `setup.command` dulu. Kalau ada, jalankan `.venv/bin/python -m etsy_insights kenali|export`.
- `keywords.txt`: berisi beberapa baris komentar `#` yang menjelaskan format, tanpa keyword.
- `README.md` (Indonesia):
  1. Unzip.
  2. Pembukaan pertama: klik kanan → Open, atau `xattr -dr com.apple.quarantine <folder>`.
  3. `setup.command`.
  4. `kenali.command`: Chrome "Etsy Riset" terbuka → login → cari 2–3 keyword di Marketplace Insights → tekan Enter di Terminal setelah setiap hasil muncul → ketik `selesai` → kirim file `rekaman/kenali-*.json` beserta screenshot ke Claude.
  5. Catatan risiko akun (ringkasan spec §14).
  6. Tahap berikutnya.

- [ ] **Step 1: Tulis test yang gagal di `tests/test_cli.py`**

```python
import subprocess
from pathlib import Path
from openpyxl import load_workbook
from etsy_insights.__main__ import main
from tests.helpers import T0

def project(tmp_path, keywords="boho wall art\nmacrame\n", config=""):
    (tmp_path / "keywords.txt").write_text(keywords, encoding="utf-8")
    (tmp_path / "config.toml").write_text(config, encoding="utf-8")
    return tmp_path

def test_cli_status(tmp_path, capsys):
    assert main(["status"], base_dir=project(tmp_path), now=lambda: T0) == 0
    out = capsys.readouterr().out
    assert "Antrean: 2 menunggu" in out and "Hari ini: 0/50 keyword dicek" in out

def test_cli_export(tmp_path, capsys):
    assert main(["export"], base_dir=project(tmp_path), now=lambda: T0) == 0
    path = tmp_path / "hasil" / "peluang-2026-11-11.xlsx"
    assert path.exists() and load_workbook(path)["Antrean"].max_row == 4

def test_cli_bad_config_returns_1(tmp_path, capsys):
    assert main(["status"], base_dir=project(tmp_path, config="kuota_harian = = 1\n"), now=lambda: T0) == 1
    out = capsys.readouterr().out
    assert "baris 1" in out and "Traceback" not in out

def test_command_scripts_are_valid_and_executable():
    for name in ("setup.command", "kenali.command", "export.command"):
        p = Path(name)
        assert p.stat().st_mode & 0o111, name
        assert subprocess.run(["bash", "-n", name]).returncode == 0
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_cli.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implementasi `__main__.py`, skrip `.command` (`chmod +x`), `keywords.txt`, dan `README.md`** sesuai aturan di atas.
- [ ] **Step 4: Jalankan semua test + smoke**

Run: `.venv/bin/pytest -q && CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest -q -m smoke`
Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: CLI (status, export, kenali), Mac launchers and README"
```

- [ ] **Step 6: Buat paket kiriman dan pastikan bit executable ikut**

Run: `git archive --format=zip --prefix=etsy-insights/ -o /home/user/etsy-insights-tahap1.zip HEAD && zipinfo /home/user/etsy-insights-tahap1.zip | grep command`
Expected: tiga file `.command` tercantum dengan izin `-rwxr-xr-x`.
