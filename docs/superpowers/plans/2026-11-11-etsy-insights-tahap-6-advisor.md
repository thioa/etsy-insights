# Etsy Insights — Tahap 6 (AI Advisor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menu **Advisor** baru. Satu klik **Get advice** menjalankan dua permintaan ke Claude:

1. cek tren lewat web;
2. analisis data aplikasi dengan jawaban JSON tetap.

Hasilnya laporan berisi rekomendasi produk/tema dan keyword usulan yang bisa dimasukkan ke antrean dengan satu
klik. Angka di laporan selalu diambil dari database.

**Architecture:**
- `advisor_brief.py` menyusun ringkasan data (fungsi murni).
- `advisor_ai.py` adalah satu-satunya modul yang mengenal library `anthropic`.
- `advisor_result.py` memvalidasi jawaban AI.
- `advisor_store.py` menyimpan laporan di `etsy.db`.
- `AdvisorJob` (`advisor.py`) menjalankan semuanya di thread latar, dengan pola `SyncJob` Tahap 4.
- `web/advisor.py` menyajikan halaman dan API.

**Tech Stack:** Python 3.11+, Flask 3, SQLite (WAL), `anthropic>=2.8,<3` (baru), pytest, Playwright (smoke).

**Spec:** `docs/superpowers/specs/2026-11-11-etsy-insights-ai-advisor-design.md`

## Global Constraints

- Semua teks UI berbahasa Inggris; README dan pesan chat berbahasa Indonesia.
- Model hanya lewat konstanta `MODEL = "claude-opus-5-5"`. Effort selalu eksplisit: langkah 1 `medium`,
  langkah 2 `high`. Adaptive thinking. Streaming + `get_final_message()`.
- Fallback: endpoint beta, `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`.
- Pencarian web hanya di langkah 1: tool `web_search_20260209`, `max_uses: 5`, lokasi perkiraan `US`.
- API key: file `anthropic-key` (0600). Key tidak pernah sampai ke browser, log, Excel, rekaman, atau pesan error.
- Semua `/api/advisor/*` wajib `X-App-Token` (POST lewat penjaga yang ada, GET dicek sendiri).
- Hanya satu analisis berjalan. Batas bulanan bawaan US$10 (0 = tanpa batas).
- AI tidak pernah memasukkan keyword ke antrean; hanya klik pengguna. Aturan sesi Etsy tidak berubah.
- Tes tidak pernah menghubungi Anthropic, Etsy, atau Printify. Klien di tes: `trust_env=False`, `max_retries=0`.
- Perintah tes memakai `.venv/bin/pytest`.
- Commit diakhiri baris atribusi dari system reminder; tanpa nama model di isi commit.

## Review Focus

1. **Database besar** (puluhan ribu keyword panen, ribuan yang sudah dicari) → ringkasan tetap ≤ 200 keyword
   dan ≤ 3.000 keyword yang ada, dan selesai < 2 detik. Dites di Task 3 `test_brief_caps_large_database`.
2. **Keyword usulan dengan huruf besar, tanda baca, atau bentuk jamak** (`"Dog Mom Tumblers!"`) → dirapikan
   menjadi `dog mom tumblers` dan tetap cocok dengan kategori Tumblers. Dites di Task 5
   `test_keyword_ideas_filtered`.
3. **Error di tengah streaming** (HTTP 200, lalu event `error` `overloaded_error`) → `ClaudeBusy`, bukan crash.
   Dites di Task 4 `test_error_mapping`.
4. **Laporan lama yang menyebut kategori atau keyword yang sudah tidak ada** (setelah Sync ulang atau keyword
   dihapus) → halaman tetap tampil dengan "—". Dites di Task 7 `test_report_with_missing_data`.
5. **Batas bulan dan zona waktu** (laporan 31 Okt 23:30 waktu lokal disimpan sebagai UTC 1 Nov) → dihitung ke
   bulan lokal Oktober. Dites di Task 2 `test_month_spend_uses_local_month`.

---

### Task 1: File rahasia, API key, dan library `anthropic`

**Files:**
- Create: `etsy_insights/secret_file.py`, `etsy_insights/advisor_key.py`
- Modify: `etsy_insights/printify_token.py` (memakai `secret_file`), `requirements.txt`
- Test: `tests/test_advisor_key.py` (baru); `tests/test_printify_token.py` tetap lulus tanpa perubahan

**Interfaces:**
- Produces:
  - `save_secret(home: Path, name: str, value: str) -> None`: tulis atomik `.<name>.tmp` (0600) lalu
    `os.replace`. Membuat `home` kalau belum ada.
  - `load_secret(home: Path, name: str) -> str | None`: isi file, atau `None` kalau tidak ada.
  - `delete_secret(home: Path, name: str) -> None`
  - `KEY_FILE = "anthropic-key"`
  - `clean_key(text: str) -> str`: buang semua spasi dan baris baru.
  - `looks_like_key(key: str) -> bool`: diawali `sk-ant-`, panjang ≥ 20, semua karakter ASCII 33–126.
  - `save_key(home, key) -> str`: membersihkan, memeriksa (kalau gagal `ValueError("That does not look like an
    Anthropic API key.")`), menyimpan, lalu mengembalikan key bersih.
  - `load_key(home) -> str | None` (sudah dibersihkan; kosong → `None`)
  - `delete_key(home) -> None`
  - `key_hint(key) -> str`: `"…" + key[-4:]`

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_advisor_key.py`):
  - `test_clean_and_shape`: `clean_key(" sk-ant-api03-abc\n def ")` sama dengan `"sk-ant-api03-abcdef"`.
    `looks_like_key` bernilai False untuk `"sk-ant-short"`, `"sk-proj-" + "a"*30`, dan key berisi `é`.
    Bernilai True untuk `"sk-ant-api03-" + "a"*20`.
  - `test_save_load_delete_permissions`:
    - `save_key` → file `home/"anthropic-key"` ada dengan mode `0o600`;
    - `load_key` sama dengan key bersih;
    - `delete_key` → `load_key is None`;
    - `delete_key` kedua kali tidak error.
  - `test_save_rejects_bad_key`: `save_key(home, "hello")` → `ValueError` dan file tidak dibuat.
  - `test_key_hint`: `key_hint("sk-ant-api03-xyz1234") == "…1234"`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_advisor_key.py -q`. Expected: FAIL
  (modul belum ada).
- [ ] **Step 3: Implementasi.**
  - `secret_file.py`, diambil dari kode `printify_token.save_token`/`load_token`/`delete_token`.
  - `printify_token.py` memanggil `secret_file`; fungsi publik dan pesannya tetap.
  - `advisor_key.py`.
  - `requirements.txt` ditambah baris `anthropic>=2.8,<3`, lalu jalankan `.venv/bin/pip install -r requirements.txt`.
- [ ] **Step 4: Jalankan.**
  - Run: `.venv/bin/pytest tests/test_advisor_key.py tests/test_printify_token.py -q`. Expected: semua PASS.
  - Run: `.venv/bin/python -c "import anthropic; print(anthropic.__version__)"`. Expected: `2.8.0` atau lebih baru
    di bawah 3.
- [ ] **Step 5: Commit.** `git commit -m "feat: shared secret file and Anthropic API key storage"`

---

### Task 2: Penyimpanan laporan, batas bulanan, dan Settings

**Files:**
- Create: `etsy_insights/advisor_store.py`
- Modify: `etsy_insights/store.py` (jalankan `ADVISOR_SCHEMA`), `etsy_insights/config.py`,
  `etsy_insights/settings.py`, `etsy_insights/web/templates/settings.html`
- Test: `tests/test_advisor_store.py` (baru), `tests/test_config.py`, `tests/test_settings.py`

**Interfaces:**
- Produces:
  - `ADVISOR_SCHEMA`: SQL spec §8.
  - `Source(id: str, url: str, title: str)` (frozen dataclass; `id` = `"S1"`, `"S2"`, …)
  - `Usage(input_tokens: int = 0, output_tokens: int = 0, web_searches: int = 0, cost_cents: int = 0)`
    (frozen), dengan `__add__` yang menjumlahkan semua field.
  - `Report`, frozen dataclass dengan field:
    - `id`, `started_at: datetime`, `finished_at: datetime | None`;
    - `status` (`running|done|error|interrupted`), `stage: str | None`;
    - `model: str | None`, `error: str | None`;
    - `trend_note: str | None`, `trend_failed: bool`, `sources: tuple[Source, ...]`;
    - `result: dict | None`, `stats: dict`;
    - `usage: Usage`.
  - `AdvisorStore(store: Store)`, metode:
    - `start_report(now: datetime, model: str) -> int`
    - `set_stage(report_id: int, stage: str) -> None`
    - `finish_report(report_id, now, *, trend_note: str | None, trend_failed: bool, sources: Sequence[Source],
      result: dict, stats: dict, usage: Usage) -> None` → status `done`, `stage` NULL
    - `fail_report(report_id, now, error: str, usage: Usage, *, trend_note=None, trend_failed=False,
      sources=()) -> None` → status `error`
    - `mark_interrupted() -> int` (jumlah baris `running` yang diubah)
    - `report(report_id: int) -> Report | None`
    - `reports(limit: int = 20) -> list[Report]` (terbaru dulu)
    - `month_spend(now: datetime) -> tuple[int, int]`: (jumlah laporan, total sen) di bulan kalender lokal
      `now`, semua status.
  - `Config.advisor_batas_bulanan_usd: float = 10.0`, rentang 0–1000 atau nilai bawaan + peringatan.
  - `settings.SELLING_FIELDS["advisor_batas_bulanan_usd"] = (0, 1000, "Enter an amount from 0 to 1000.")`,
    juga di `FORM_FIELDS` dan `settings_form`.
- Waktu disimpan sebagai ISO UTC, seperti `store._ts`/`_dt`.

- [ ] **Step 1: Tulis tes yang gagal.**
  - `tests/test_advisor_store.py`:
    - `test_report_lifecycle`:
      - `start_report` → `report(id).status == "running"` dan `model == "claude-opus-5-5"`;
      - `set_stage(id, "analyzing")`;
      - `finish_report` dengan dua `Source`, `result={"summary": "x", ...}`, `stats={"keywords": 3}`, dan
        `Usage(1000, 200, 2, 9)`;
      - hasilnya: status `done`, `stage is None`, sumber dan hasil kembali sama persis, dan `finished_at` terisi.
    - `test_fail_keeps_cost`: `fail_report(..., "Claude is busy.", Usage(cost_cents=12))` → status `error`,
      `error` sesuai, `usage.cost_cents == 12`.
    - `test_mark_interrupted_and_order`: dua laporan `running` → `mark_interrupted() == 2`, status
      `interrupted`, dan `reports()` terbaru dulu.
    - `test_month_spend_uses_local_month`: zona `UTC+7`. Laporan 2026-10-31 23:30 lokal biaya 50 dan
      2026-11-01 00:10 lokal biaya 30 → `month_spend(2026-11-11 lokal) == (1, 30)` dan
      `month_spend(2026-10-15 lokal) == (1, 50)`.
    - `test_old_database_gets_table`: database Tahap 5 (dibuat tanpa tabel advisor) dibuka dengan `Store` →
      `AdvisorStore(store).reports() == []`.
    - `test_usage_add`: `Usage(1,2,3,4) + Usage(10,20,30,40) == Usage(11,22,33,44)`.
  - `tests/test_config.py`: `advisor_batas_bulanan_usd` bawaan 10.0. Nilai `2000` dan `-1` → nilai bawaan +
    peringatan. `0` diterima.
  - `tests/test_settings.py`:
    - formulir dengan `advisor_batas_bulanan_usd = "25"` → tersimpan 25 di `config.toml`;
    - `"abc"` → error `"Enter an amount from 0 to 1000."`;
    - formulir tanpa field ini → nilai sekarang tetap;
    - halaman Settings memuat legend `Advisor`, label `Advisor monthly limit (USD)`, dan keterangan
      `0 means no limit. Each run costs about US$0.40–0.80.`
- [ ] **Step 2: Jalankan, pastikan gagal.** Run:
  `.venv/bin/pytest tests/test_advisor_store.py tests/test_config.py tests/test_settings.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi.**
  - `advisor_store.py` memakai pola `printify_store` (import `Store` hanya untuk `TYPE_CHECKING`).
  - `Store.__init__` menjalankan `ADVISOR_SCHEMA` setelah `PRINTIFY_SCHEMA`.
  - `month_spend` membaca semua baris lalu memfilter di Python dengan `started_at.astimezone(now.tzinfo)`.
    Jumlah laporan kecil, jadi ini cukup.
  - Settings: fieldset baru `Advisor` setelah `Selling on Etsy`, dengan pola isian yang sama.
- [ ] **Step 4: Jalankan.** Run yang sama. Expected: semua PASS. Run: `.venv/bin/pytest -q -m "not smoke"`.
  Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: advisor report storage and monthly limit setting"`

---

### Task 3: Ringkasan data (`advisor_brief.py`)

**Files:**
- Create: `etsy_insights/advisor_brief.py`
- Modify: `etsy_insights/catalog.py` (ganti nama `_CategoryIndex` → `CategoryIndex`, publik),
  `etsy_insights/store.py` (`searched_or_queued`)
- Test: `tests/test_advisor_brief.py`

**Interfaces:**
- Consumes:
  - `categories_from`, `summarize`, `CategoryIndex`, `OTHER` (catalog);
  - `score_all`, `ScoredKeyword`;
  - `build_profiles`, `fits_for_store`;
  - `PrintifyStore`;
  - `remaining_quota`;
  - `CONVERSION_LEVEL_TEXT`.
- Produces:
  - `Store.searched_or_queued(limit: int) -> list[str]`: keyword berstatus `pending`, `in_progress`, `done`,
    `no_data`, urut `COALESCE(last_checked_at, added_at)` menurun.
  - `TAKEN_STATUSES = ("pending", "in_progress", "done", "no_data")` (di `advisor_brief`).
  - `trend_pct(trend: Sequence[float]) -> float | None`: rata-rata 7 titik terakhir dibandingkan rata-rata
    semua titik sebelumnya, dalam %, dibulatkan 1 desimal. Kurang dari 14 titik, atau rata-rata lama ≤ 0 →
    `None`.
  - `select_keywords(scored: Sequence[ScoredKeyword], cfg: Config, limit: int = 200, rising_limit: int = 60)
    -> list[ScoredKeyword]`: urutan spec §6.2 (naik ≥ +20% dengan volume ≥ `volume_minimum` sampai 60, urut
    tren menurun; lalu `eligible` dengan skor tertinggi; lalu volume tertinggi). Tanpa duplikat.
  - `TrendInput(today: date, categories: tuple[str, ...], top_keywords: tuple[str, ...])`.
    `categories` = nama tampilan, urut nama, tanpa *Other*. `top_keywords` = 20 keyword `eligible` dengan
    skor tertinggi.
  - `AnalysisInput(payload: dict, category_keys: tuple[str, ...], keyword_count: int, category_count: int)`
  - `build_inputs(store: Store, cfg: Config, now: datetime) -> tuple[TrendInput, AnalysisInput]`
  - Bentuk `payload` (kunci JSON, bahasa Inggris):
    - `context`: `today`, `market` (`"Etsy buyers in the United States; free shipping"`), `daily_searches`,
      `searches_left_today`, `in_queue`, `etsy_fee_percent`, `etsy_fixed_fee_usd`, `minimum_margin_usd`.
    - `categories[]`: `key`, `name`, `models`, `in_my_products`, `production_cost_usd` (`"5.12–7.00"`, atau
      `null`), `keywords_with_data`, `gold`, `potential`, `most_searched` (`{keyword, volume}` atau `null`),
      `ready_to_sell` (`int` atau `null`), `research`.
    - `keywords[]`: `keyword`, `category` (kunci pertama dari `CategoryIndex`, atau `null`), `volume`,
      `conversion` (teks level), `competition`, `searches_per_listing`, `score`, `label`, `trend_pct`,
      `week_change_pct`, `margin_usd`, `ready_to_sell`, dan `buyers` kalau ada profil. `buyers` berisi
      `paid_price`, `difficulty`, `top_words` (5), `median_reviews`, dan `bestseller_share`.
    - `existing_keywords[]`: `searched_or_queued(3000)`.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_advisor_brief.py`; data dari `seeded_home`,
  `seed_printify`, `seed_ready_keyword`, dan `tests/helpers.make_row`):
  - `test_trend_pct`:
    - `[10]*7 + [20]*7` → `100.0`;
    - `[10]*10 + [5]*7` → `-50.0`;
    - 13 titik → `None`;
    - `[0]*7 + [5]*7` → `None`.
  - `test_select_keywords_order_and_caps`:
    - 70 baris naik (tren +50%, volume 500) dan 300 baris *eligible* biasa;
    - hasilnya 200 baris, 60 pertama adalah baris naik dengan tren terbesar dulu, dan tidak ada duplikat;
    - baris naik dengan volume di bawah `volume_minimum` tidak masuk kelompok naik.
  - `test_inputs_for_fixture_data`:
    - `TrendInput.today == now.date()`;
    - `"Mugs"` ada di `categories`, `"Other"` tidak;
    - `top_keywords` ≤ 20;
    - `payload["context"]["daily_searches"] == 15`;
    - kategori `mug` memiliki `production_cost_usd == "5.12–5.12"` dan `in_my_products is True`;
    - `custom mug` ada di `keywords` dengan `category == "mug"` dan `ready_to_sell is True`;
    - `category_keys` tidak memuat `"other"`.
  - `test_existing_keywords_exclude_harvested`: keyword panen dari fixture tidak ada di `existing_keywords`;
    keyword pengguna yang `done` dan `pending` ada.
  - `test_brief_has_no_private_data`: setelah `save_token(home, "secret-printify-token-1")` dan
    `save_key(home, "sk-ant-api03-" + "z"*20)`, `json.dumps(payload) + repr(trend_input)` tidak memuat
    token, key, `"etsy.com/listing"`, atau nama toko mana pun dari `ListingCard.shop` di profil fixture.
  - `test_brief_caps_large_database`:
    - 30.000 keyword panen dan 5.000 keyword `done` dimasukkan langsung lewat SQL;
    - `len(keywords) <= 200` dan `len(existing_keywords) == 3000`;
    - `build_inputs` selesai < 2 detik (`time.perf_counter`).
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_advisor_brief.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi.**
  - Ringkasan kategori diambil dari `summarize(store, cfg, categories_from(printify.blueprints()))`.
  - Kisaran biaya per kategori diambil dari `printify.types(include_unavailable=False)` yang punya
    `cost_min_cents`, dikelompokkan dengan `category_for(t.title)`.
  - Margin dan *Ready to sell* hanya untuk keyword terpilih: `build_profiles(store, only=selected)` lalu
    `fits_for_store`.
  - `searches_left_today = remaining_quota(cfg, store.checked_on(today, tz))`.
  - `in_queue` = jumlah keyword `pending` + `in_progress`.
  - Angka uang ditulis sebagai teks dua desimal; persentase dibulatkan 1 desimal.
  - Rename `CategoryIndex` di `catalog.py` adalah perubahan nama saja.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_advisor_brief.py tests/test_catalog.py -q`.
  Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: advisor data brief (keywords, categories, trends, privacy)"`

---

### Task 4: Server Anthropic palsu dan klien Claude (`advisor_ai.py`)

**Files:**
- Create: `tests/anthropic_fake.py`, `etsy_insights/advisor_ai.py`
- Test: `tests/test_advisor_ai.py`

**Interfaces:**
- Consumes: `Source`, `Usage` (Task 2); `TrendInput`, `AnalysisInput` (Task 3); `default_ssl_context`
  (`printify_api`).
- Produces (`tests/anthropic_fake.py`):
  - `FakeAnthropic(tls: tuple | None = None)`: context manager. Atributnya:
    - `.url`;
    - `.requests: list[dict]` dengan kunci `method`, `path`, `headers`, `body` (JSON ter-parse).
  - Metode `FakeAnthropic`:
    - `.queue(method, path, *responses)`: dipakai berurutan;
    - `.set(method, path, response)`: jawaban bawaan kalau antrean kosong.
  - Bawaan:
    - `GET /v1/models/claude-opus-5-5` → 200 `model_body()`;
    - yang lain → 404 `error_body("not_found_error", ...)`.
  - Respons: `Sse(events: list[dict])`, `Json(status: int, body: dict)`, `DROP` (koneksi ditutup tanpa jawaban).
  - Pembuat event:
    - `message_events(blocks: list[dict], *, stop_reason="end_turn", model="claude-opus-5-5",
      input_tokens=1000, output_tokens=500, web_searches=0) -> list[dict]`: `message_start`, lalu blok-blok.
      Blok `text` memakai `text_delta` dan `citations_delta`; blok lain dikirim utuh di `content_block_start`.
      Diakhiri `message_delta` dan `message_stop`.
    - `text_block(text, citations=())`, dengan `citations` berupa daftar `(url, title)`;
    - `search_blocks(query, results)` → `[server_tool_use, web_search_tool_result]`;
    - `error_body(type, message)`, `model_body()`, `error_event(type, message)`.
- Produces (`etsy_insights/advisor_ai.py`):
  - Konstanta:
    - `MODEL = "claude-opus-5-5"`, `BASE_URL = "https://api.anthropic.com"`;
    - `FALLBACK_BETA = "server-side-fallback-2026-07-01"`, `MAX_SEARCHES = 5`, `MAX_CONTINUES = 3`;
    - `PRICES = {"claude-opus-5-5": (400, 2000), "claude-opus-5": (500, 2500), "claude-opus-4-8": (500, 2500)}`
      (sen per juta token input/output), `SEARCH_CENTS = 1`.
  - `cost_cents(model: str, input_tokens: int, output_tokens: int, web_searches: int) -> int`:
    `ceil((in*harga_in + out*harga_out) / 1_000_000) + web_searches*SEARCH_CENTS`. Model tak dikenal memakai
    harga tertinggi di tabel.
  - `ClaudeError(Exception)`: `.message: str`, `.usage: Usage` (yang sudah terpakai, bawaan `Usage()`).
    Subkelasnya beserta pesan spec §7:
    - `KeyRejected`, `NoModelAccess`;
    - `ClaudeRequestFailed`, `ClaudeBusy`;
    - `ClaudeUnreachable`, `ClaudeCertificateProblem`;
    - `ClaudeRefused`, `ClaudeCutOff`, `ClaudeBadAnswer`.
  - `TrendResult(note: str, sources: tuple[Source, ...], usage: Usage)`
  - `AnalysisResult(data: dict, usage: Usage, model: str)`
  - `answer_schema(category_keys: Sequence[str]) -> dict`: skema spec §6.3. `kind` memakai enum
    `["from_data", "season", "trend", "new_niche"]`. Semua objek `additionalProperties: False`, dan semua field
    `required`.
  - `AdvisorAI(key: str, *, base_url: str = BASE_URL, ssl_context: ssl.SSLContext | None = None,
    trust_env: bool = True, max_retries: int = 2, timeout: float = 600)`. Membuat
    `anthropic.Anthropic(api_key=key, base_url=base_url, max_retries=…, timeout=…,
    http_client=anthropic.DefaultHttpxClient(verify=ssl_context or default_ssl_context(), trust_env=…))`.
    Metode:
    - `test_key() -> None`: `models.retrieve(MODEL)`.
    - `check_trends(inp: TrendInput) -> TrendResult`: `max_tokens=32000`, effort `medium`, tool pencarian web.
      `pause_turn` dilanjutkan dengan mengirim ulang `messages + [{"role": "assistant", "content":
      [b.to_dict() for b in message.content]}]`. Kalau masih `pause_turn` setelah `MAX_CONTINUES` →
      `ClaudeCutOff`.
    - `analyze(inp: AnalysisInput, trend: TrendResult | None) -> AnalysisResult`: `max_tokens=64000`, effort
      `high`, `output_config.format = {"type": "json_schema", "schema": answer_schema(inp.category_keys)}`,
      tanpa tool.
  - **Prompt** (bahasa Inggris, konstanta `TREND_SYSTEM` dan `ANALYSIS_SYSTEM`). Isinya aturan spec §6.1 dan
    §6.2. Pesan pengguna:
    - langkah 1: tanggal, pasar, nama kategori, dan keyword teratas;
    - langkah 2: `<shop_data>` + JSON payload (`ensure_ascii=False`), lalu `<trend_notes>` berisi catatan tren
      dan daftar `S1: title — url`, atau kalimat bahwa tidak ada catatan tren.
  - **Sumber:** dari `citations` bertipe `web_search_result_location` di blok `text`. Kalau tidak ada kutipan,
    diambil dari isi `web_search_tool_result`. Hanya `http`/`https`, tanpa URL ganda, maksimal 10, diberi
    nomor `S1…`.
  - **Catatan tren:** gabungan teks blok `text` dari semua respons, `strip()`, maksimal 6.000 karakter.
  - **Pemetaan error** sesuai spec §7:
    - `APIStatusError` lain (termasuk error di tengah streaming dengan `status_code` 200): tipe di
      `exc.body["error"]["type"]` `overloaded_error`/`api_error` → `ClaudeBusy`; selain itu
      `ClaudeRequestFailed`.
    - Sertifikat: rantai `__cause__`/`__context__` berisi `ssl.SSLCertVerificationError` →
      `ClaudeCertificateProblem`, dengan teks pesan sama seperti `printify_api.CertificateProblem` tapi
      menyebut "Anthropic".
    - Pesan Anthropic diambil dari `exc.body["error"]["message"]` (cadangan: `str(exc)`), dipangkas
      300 karakter, lalu `re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "…", text)`.
  - **Usage:**
    - `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` → input;
    - `output_tokens`;
    - `server_tool_use.web_search_requests` (kalau `None`, 0);
    - harga menurut `message.model`.

    Error karena `stop_reason` membawa usage respons itu ditambah usage dari kelanjutan sebelumnya.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_advisor_ai.py`). Klien di tes:
  `AdvisorAI("sk-ant-test-key-123456", base_url=fake.url, trust_env=False, max_retries=0)`.
  - `test_test_key`: ok tanpa error. Lalu:
    - antre 401 → `KeyRejected`;
    - 403 → `NoModelAccess`;
    - 404 → `NoModelAccess`;
    - `DROP` → `ClaudeUnreachable`.
  - `test_check_trends_request_and_sources`. Respons: `search_blocks` dengan 2 hasil, lalu `text_block` dengan
    3 kutipan (satu URL ganda, satu `javascript:`), dan `web_searches=1`. Yang diperiksa:
    - `note` berisi teksnya;
    - `sources` = 2 `Source` (`S1`, `S2`) dengan URL `https`;
    - `usage.web_searches == 1`.
    - Isi permintaan:
      - `model == "claude-opus-5-5"`, `max_tokens == 32000`, `thinking == {"type": "adaptive"}`;
      - `output_config == {"effort": "medium"}`;
      - `tools == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5,
        "user_location": {"type": "approximate", "country": "US"}}]`;
      - `fallbacks == "default"`;
      - header `anthropic-beta` memuat `server-side-fallback-2026-07-01`;
      - pesan pengguna memuat nama kategori dan tanggal.
  - `test_sources_from_search_results`: tanpa kutipan → sumber dari hasil pencarian, maksimal 10, hanya `http(s)`.
  - `test_pause_turn_continues`:
    - respons 1 `pause_turn`, respons 2 `end_turn` → 2 permintaan; permintaan kedua punya 2 pesan dan pesan
      kedua `role == "assistant"`; `usage.input_tokens == 2000`.
    - 4 respons `pause_turn` → `ClaudeCutOff` setelah 4 permintaan.
  - `test_analyze_request_and_parse`. Respons berupa JSON valid. Hasilnya:
    - `data` sama dengan JSON itu;
    - `model == "claude-opus-5-5"`.
    - Isi permintaan:
      - `max_tokens == 64000`;
      - `output_config["effort"] == "high"`;
      - `output_config["format"]["schema"]["properties"]["recommendations"]["items"]["properties"]["category"]["enum"]
        == ["mug", "tumbler"]`;
      - tidak ada `tools`;
      - pesan pengguna memuat `<shop_data>` dan `S1:`.
  - `test_analyze_bad_answers`: teks bukan JSON → `ClaudeBadAnswer`. JSON tanpa `keyword_ideas` →
    `ClaudeBadAnswer`.
  - `test_stop_reasons_keep_usage`:
    - `refusal` → `ClaudeRefused` dengan `exc.usage.output_tokens == 500`;
    - `max_tokens` → `ClaudeCutOff`.
  - `test_error_mapping`:
    - 400 `"Your credit balance is too low..."` → `ClaudeRequestFailed`, pesan memuat `credit balance`;
    - 429 → `ClaudeBusy`, memuat pesan Anthropic;
    - 500 dan 529 → `ClaudeBusy`;
    - SSE `message_start` lalu `error_event("overloaded_error", "Overloaded")` → `ClaudeBusy`;
    - 401 → `KeyRejected`;
    - 400 yang pesannya memuat `sk-ant-test-key-123456` → pesan aplikasi tidak memuat key.
  - `test_certificate_problem`:
    - `FakeAnthropic(tls=(cert, key))` dengan sertifikat buatan `openssl` (pola `test_catalog_smoke`), tanpa
      `ssl_context` khusus → `test_key()` memunculkan `ClaudeCertificateProblem`;
    - dengan `ssl.create_default_context(cafile=cert)` → berhasil.
  - `test_cost_cents`:
    - `cost_cents("claude-opus-5-5", 1_000_000, 100_000, 2) == 602`;
    - model `"claude-x"` → `752`;
    - `cost_cents(MODEL, 1, 0, 0) == 1`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_advisor_ai.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** `tests/anthropic_fake.py` (pola `printify_fake.py`, `ThreadingHTTPServer`;
  SSE = `event: <type>\ndata: <json>\n\n`) dan `advisor_ai.py`.
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_advisor_ai.py -q`. Expected: semua PASS, tanpa
  koneksi keluar.
- [ ] **Step 5: Commit.** `git commit -m "feat: Claude client for the advisor (trends with web search, structured analysis)"`

---

### Task 5: Validasi hasil dan `AdvisorJob`

**Files:**
- Create: `etsy_insights/advisor_result.py`, `etsy_insights/advisor.py`
- Test: `tests/test_advisor_result.py`, `tests/test_advisor_job.py`

**Interfaces:**
- Consumes:
  - `Usage`, `Source`, `AdvisorStore` (Task 2);
  - `build_inputs`, `TAKEN_STATUSES` (Task 3);
  - `AdvisorAI`, `ClaudeError`, `KeyRejected`, `NoModelAccess`, `MODEL` (Task 4);
  - `load_key` (Task 1);
  - `ENTRIES`, `matches`.
- Produces (`advisor_result.py`):
  - `clean_idea(text: str) -> str`: buang karakter selain huruf, angka, spasi, `'`, `-`, `&`, lalu
    `normalize_keyword`.
  - `Validated(result: dict, dropped: dict[str, int])`
  - `validate(raw: dict, *, categories: Collection[str], with_data: Collection[str], taken: Collection[str],
    source_ids: Collection[str]) -> Validated`. Bentuk `result`:
    - `summary`;
    - `recommendations[]`: `title`, `category`, `theme`, `why`, `evidence: list[str]`, `sources: list[str]`,
      `action`, `backed: bool`;
    - `keyword_ideas[]`: `keyword`, `category`, `kind`, `reason`.

    Kunci `dropped`: `recommendations`, `evidence`, `sources`, `ideas`. Batas dan pemangkasan sesuai spec §6.4.
  - `idea_status(keyword: str, statuses: Mapping[str, str]) -> str`:
    - `pending`/`in_progress` → `"in_queue"`;
    - `done`/`no_data` → `"researched"`;
    - selain itu → `"new"`.
- Produces (`advisor.py`):
  - `AdvisorError(Exception)` dengan `.message` dan `.status`. Subkelasnya:
    - `NotConnected` (400, `"Connect Claude first."`);
    - `NoCatalog` (400, `"Sync Printify first."`);
    - `LimitReached` (403, `"You reached this month's Advisor limit (US$10.00). Raise it in Settings or wait
      until next month."`);
    - `AdvisorBusy` (409, `"Advice is already running."`).
  - `default_ai(key: str) -> AdvisorAI`
  - `AdvisorJob(home: Path, ai_factory: Callable[[str], AdvisorAI], *, now=…, spawn=_thread)`. Saat dibuat,
    langsung `mark_interrupted()`. Metode:
    - `start() -> int`: memeriksa key, katalog (`PrintifyStore.has_blueprints()`), dan batas bulanan
      (`month_spend`), lalu `start_report` dan `spawn(lambda: self.run_now(report_id))`.
    - `status() -> dict`: `state` (`idle|running|done|error`), `stage`, `elapsed_seconds`, `report_id`, `error`.
    - `run_now(report_id: int) -> None`.
  - Alur `run_now`:
    1. `build_inputs`.
    2. Stage `checking_trends`, lalu `check_trends`. `ClaudeError` selain `KeyRejected`/`NoModelAccess` →
       `trend_failed`, usage-nya tetap dijumlahkan.
    3. Stage `analyzing`, lalu `analyze`.
    4. `validate`, dengan:
       - `categories = inp.category_keys`;
       - `with_data` = keyword di `payload["keywords"]` ditambah semua keyword berhasil dari
         `store.latest_results()`;
       - `taken` = keyword berstatus `TAKEN_STATUSES`;
       - `source_ids` dari sumber tren.
    5. `finish_report`. `stats` = `{"keywords": …, "categories": …, "dropped": …}`.

    Kalau ada `ClaudeError` di langkah 2 atau 3 → `fail_report(message, usage)`. Pengecualian lain →
    `fail_report("Something went wrong. See the log for details.")` dan `log.exception` (tanpa key).

- [ ] **Step 1: Tulis tes yang gagal.**
  - `tests/test_advisor_result.py`. Data uji:
    - `categories={"mug", "tumbler", "t shirt"}`;
    - `with_data={"custom mug", "dog mom sweatshirt"}`;
    - `taken={"custom mug", "teacher mug"}`;
    - `source_ids={"S1", "S2"}`.

    Tes:
    - `test_recommendations_validated`:
      - evidence `["Custom Mug", "unknown"]` → `["custom mug"]` dan `backed is True`;
      - tanpa evidence valid → `backed is False`;
      - `sources ["S1", "S9"]` → `["S1"]`;
      - kategori `"poster"` → dibuang (`dropped["recommendations"] == 1`);
      - 10 rekomendasi → 8;
      - `title` 500 karakter → 120.
    - `test_keyword_ideas_filtered`:
      - `"Dog Mom Tumblers!"` (tumbler) → `"dog mom tumblers"`;
      - `"teacher mug"` → dibuang;
      - ide ganda → dibuang;
      - 7 kata → dibuang;
      - `"retro sunset"` (t shirt) → dibuang;
      - `"cat dad shirt"` (t shirt) → tetap;
      - kategori tak dikenal → dibuang;
      - keyword panen yang tidak ada di `taken` → tetap;
      - 25 ide valid → 20;
      - `reason` dipangkas 300.
    - `test_summary_truncated`: 2.000 karakter → 1.200.
    - `test_idea_status`: tiga keadaan, ditambah `harvested` → `"new"`.
  - `tests/test_advisor_job.py`. `FakeAI` dibuat di dalam tes; metodenya mengembalikan atau memunculkan nilai
    yang diatur. Home disiapkan dengan `seeded_home` + `seed_printify` + `seed_ready_keyword` + `save_key`, dan
    `spawn=lambda f: f()`.
    - `test_full_run_saves_report`:
      - laporan `done`;
      - `result["keyword_ideas"]` sudah tervalidasi;
      - `usage.cost_cents` = jumlah dari kedua langkah;
      - `stats["keywords"] > 0`;
      - `sources` tersimpan;
      - `status()["state"] == "done"` dan `report_id` sesuai.
    - `test_trend_failure_continues`: `check_trends` memunculkan `ClaudeBusy` dengan `usage.cost_cents=10` →
      laporan `done`, `trend_failed is True`, biaya memuat 10, dan `analyze` dipanggil dengan `trend=None`.
    - `test_key_rejected_stops`: `check_trends` memunculkan `KeyRejected` → laporan `error` dengan pesan key
      ditolak, dan `analyze` tidak dipanggil.
    - `test_analysis_error_records_cost`: `analyze` memunculkan `ClaudeCutOff` (`usage.cost_cents=40`) →
      laporan `error`, biaya = 40 + biaya langkah 1.
    - `test_start_guards`:
      - tanpa key → `NotConnected`;
      - tanpa katalog (home tanpa `seed_printify`) → `NoCatalog`;
      - laporan bulan ini dengan biaya 1.000 sen dan batas 10 → `LimitReached`, pesan memuat `US$10.00`;
      - batas 0 → boleh;
      - `spawn=lambda f: None` lalu `start()` dua kali → `AdvisorBusy`.
    - `test_interrupted_on_restart`: baris `running` → `AdvisorJob(...)` baru menandainya `interrupted`, dan
      `status()["state"] == "idle"`.
    - `test_unexpected_exception`: `FakeAI.analyze` memunculkan `RuntimeError("boom sk-ant-xyz")` → pesan
      laporan `"Something went wrong. See the log for details."`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run:
  `.venv/bin/pytest tests/test_advisor_result.py tests/test_advisor_job.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** `advisor_result.py` dan `advisor.py`, dengan pola `SyncJob` (lock, `_set`,
  `_thread`). `elapsed_seconds` dihitung dari `started_at` laporan.
- [ ] **Step 4: Jalankan.** Run yang sama. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: advisor result validation and background job"`

---

### Task 6: API Advisor

**Files:**
- Create: `etsy_insights/web/advisor.py` (blueprint `bp`, bagian API)
- Modify: `etsy_insights/web/__init__.py`, `tests/web_helpers.py`
- Test: `tests/test_web_advisor_api.py`

**Interfaces:**
- Consumes: Task 1, 2, 5; `keywords.add_keywords`; `app_token_ok` (`web/printify.py`).
- Produces:
  - `create_app(..., advisor_client: Callable[[str], AdvisorAI] | None = None,
    advisor_spawn: Callable | None = None)`. `ctx().advisor_client` (bawaan `default_ai`) dan
    `ctx().advisor_job` (`AdvisorJob`).
  - `web_helpers.advisor_app(home, ai_factory, *, spawn=lambda f: f(), port=8765) -> (app, client)`
  - Endpoint sesuai spec §10. Respons error: `{"error": message}`.
    - `POST /api/advisor/key`: kosong → 400 `"Paste your Anthropic API key."`. Lalu `test_key`:
      - `KeyRejected`/`NoModelAccess` → 400 tanpa menyimpan;
      - `ClaudeUnreachable`/`ClaudeCertificateProblem`/`ClaudeBusy` → simpan, 200
        `{hint, warning: "Saved, but Anthropic could not be reached to test it."}`;
      - ok → simpan, 200 `{hint}`.
    - `POST /api/advisor/disconnect` → `delete_key`, 200 `{ok: true}`.
    - `POST /api/advisor/run` → 202 `{report_id}`, atau `AdvisorError.status` + pesan.
    - `GET /api/advisor/status` → `job.status()`. Tanpa `X-App-Token` → 403.
    - `POST /api/advisor/add` `{report_id, keywords}`:
      - hanya keyword yang ada di `result["keyword_ideas"]` laporan itu (setelah `clean_idea`) yang dikirim ke
        `add_keywords`;
      - 200 `{added, statuses: {keyword: idea_status}}` untuk semua ide laporan;
      - laporan tidak ada → 404 `"Report not found."`;
      - bukan daftar string → 400 `"Choose at least one keyword."`.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_web_advisor_api.py`, `FakeAI` seperti Task 5):
  - `test_save_key_paths`:
    - `"hello"` → 400 `"That does not look like an Anthropic API key."`;
    - `test_key` memunculkan `KeyRejected` → 400 dan file tidak ada;
    - `ClaudeUnreachable` → 200 dengan `warning` dan file ada;
    - ok → 200 `hint == "…3456"`;
    - teks key tidak muncul di body respons mana pun.
  - `test_disconnect`: file key hilang.
  - `test_run_and_status`:
    - 202 + `report_id`, lalu `status` `done` (spawn sinkron);
    - tanpa key → 400 `"Connect Claude first."`;
    - tanpa katalog → 400 `"Sync Printify first."`;
    - batas tercapai → 403;
    - sedang berjalan (`spawn=lambda f: None`) → 409.
  - `test_add_only_report_ideas`:
    - laporan berisi ide `"dog mom tumbler"` dan `"cat dad shirt"`;
    - `add` dengan `["Dog Mom Tumbler", "free money"]` → `added == ["dog mom tumbler"]`;
    - `keywords.txt` memuat `dog mom tumbler` tetapi tidak `free money`;
    - `statuses["dog mom tumbler"] == "in_queue"` dan `statuses["cat dad shirt"] == "new"`;
    - `add` kedua kali → `added == []` tanpa error;
    - `report_id` 999 → 404.
  - `test_token_required`:
    - `POST /api/advisor/run` tanpa token → 403;
    - `GET /api/advisor/status` tanpa header `X-App-Token` → 403, dengan header → 200.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_advisor_api.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implementasi** endpoint dan wiring `create_app` (opsi `spawn` hanya diteruskan kalau tidak
  `None`, seperti `printify_spawn`).
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_web_advisor_api.py -q` lalu
  `.venv/bin/pytest -q -m "not smoke"`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: advisor API (key, run, status, add ideas)"`

---

### Task 7: Halaman Advisor

**Files:**
- Modify: `etsy_insights/web/advisor.py` (halaman), `etsy_insights/web/templates/base.html` (menu),
  `etsy_insights/web/static/app.js`, `etsy_insights/web/static/app.css`
- Create: `etsy_insights/web/templates/advisor.html`
- Test: `tests/test_web_advisor_pages.py`

**Interfaces:**
- Consumes: Task 2, 5, 6; `trend_pct` (Task 3); `categories_from`, `category_slug`, `CATEGORY_NAMES`,
  `score_all`, `build_profiles`, `fits_for_store`, `money`.
- Produces:
  - `GET /advisor` dan `GET /advisor/<int:report_id>` (404 kalau tidak ada). Konten sesuai spec §10 dan teks
    UI spec §3.
  - `report_view(report: Report, store, cfg) -> dict` untuk template:
    - kategori → nama, slug, dan foto (`categories_from(printify.blueprints())`). Kategori yang sudah tidak ada
      → nama dari `CATEGORY_NAMES` atau kunci mentah, tanpa tautan.
    - baris evidence → volume, konversi, kompetisi, label, tren % (`trend_pct`), margin/*Ready to sell* dari
      database. Keyword yang sudah tidak ada → "—".
    - sumber → hanya `http(s)`.
    - status tiap ide → `idea_status`.
  - Atribut HTML untuk JS:
    - `data-advisor-key-form`, `data-advisor-disconnect`, `data-advisor-run`;
    - `data-advisor-status` (dengan `data-state`);
    - `data-idea` (nilai keyword) di setiap baris;
    - `data-add-idea`, `data-add-selected`, `data-report-id`.
- JS memakai `post()` dan `getJSON()` yang sudah ada:
  - Save and test → tampilkan error/warning atau muat ulang.
  - Get advice → polling `GET /api/advisor/status` tiap 2 detik selama `running`. Tampilkan
    `Step 1 of 2 – Checking trends on the web…` atau `Step 2 of 2 – Analyzing your data…` beserta waktu
    berjalan. Saat `done`/`error` → buka `/advisor/<report_id>`.
  - Kalau halaman dibuka saat `running` → polling langsung.
  - Add / Add selected → perbarui teks status baris dari `statuses`, dan sembunyikan tombol untuk yang bukan
    `new`.

- [ ] **Step 1: Tulis tes yang gagal** (`tests/test_web_advisor_pages.py`):
  - `test_not_connected`: `Connect Claude`, `console.anthropic.com`, input `type="password"`,
    `Save and test`; tidak ada `Get advice`.
  - `test_ready_states`:
    - terhubung → `…3456`, `Disconnect`, `Get advice`,
      `Uses Claude Opus 5.5 and up to 5 web searches. Est. US$0.40–0.80 per run.`, dan
      `This month: 0 runs, US$0.00`;
    - tanpa katalog → tombol `disabled` dan `Sync Printify first.`;
    - < 20 keyword dicari → teks peringatan spec §10;
    - batas tercapai → pesan batas.
  - `test_report_page`:
    - laporan `done` buatan tes (lewat `AdvisorStore`) dengan 1 rekomendasi *backed* (evidence
      `custom mug`, sumber `S1`) dan 1 *Idea*, serta ide `custom mug tumbler` dan `teacher mug`
      (berstatus `done` di DB);
    - halaman memuat `Summary`, `Backed by data`, `Idea`, tautan `/catalog/mug`, dan volume `custom mug` dari
      database (bukan dari AI);
    - tautan sumber memakai `rel="noopener noreferrer"` dan `target="_blank"`;
    - status `New` dan `Researched`;
    - `What's trending`, `Earlier reports`, `Est. cost`;
    - `Each idea uses 1 of your 15 daily searches. In queue now:` diikuti jumlah keyword `pending` +
      `in_progress`.
  - `test_report_escapes_ai_text`: `summary` dan `why` berisi `<script>alert(1)</script>`, sumber
    `javascript:alert(1)` → HTML memuat `&lt;script&gt;` dan tidak memuat `href="javascript:`.
  - `test_report_with_missing_data`: rekomendasi dengan kategori `"poster"` (tidak ada di katalog) dan evidence
    keyword yang sudah dihapus dari DB → 200, nama `Posters`, dan sel `—`.
  - `test_error_and_interrupted_reports`: laporan `error` menampilkan pesan dan `Est. cost`; laporan
    `interrupted` menampilkan `Interrupted`.
  - `test_nav_has_advisor`: urutan menu `Catalog`, `Advisor`, `Printify`.
  - `test_unknown_report_404`.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `.venv/bin/pytest tests/test_web_advisor_pages.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implementasi** template, `report_view`, menu, JS, dan CSS (pakai kelas yang ada: `panel`,
  `grid-cards`, `btn`, `muted`; tambah seperlunya untuk lencana dan tabel ide).
- [ ] **Step 4: Jalankan.** Run: `.venv/bin/pytest tests/test_web_advisor_pages.py -q` lalu
  `.venv/bin/pytest -q -m "not smoke"`. Expected: semua PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: Advisor page with reports, keyword ideas and one-click queue"`

---

### Task 8: Smoke test, README, dan paket 6.0.0

**Files:**
- Create: `tests/test_advisor_smoke.py`
- Modify: `README.md`, `macos/README.txt`
- Test: smoke (Chromium) + seluruh suite

**Interfaces:**
- Consumes: `FakeAnthropic` (Task 4), `advisor_app` (Task 6), `free_port` (`test_web_smoke`).

- [ ] **Step 1: Tulis smoke test** `test_advisor_end_to_end`.
  - **Persiapan:**
    - `FakeAnthropic()` (HTTP), antre stream langkah 1 (pencarian + teks berkutipan) dan stream langkah 2
      (JSON dengan 1 rekomendasi kategori `mug` dan 2 ide);
    - home `seeded_home` + `seed_printify` + `seed_ready_keyword`;
    - app dari `create_app` dengan
      `advisor_client=lambda k: AdvisorAI(k, base_url=fake.url, trust_env=False, max_retries=0)` dan thread
      sungguhan (`advisor_spawn=None`);
    - Playwright dengan penjaga host luar (pola `test_catalog_smoke`).
  - **Alur:**
    1. `/advisor` → isi key → **Save and test** → **Get advice**.
    2. Tunggu teks `Backed by data` (≤ 20 detik).
    3. Centang ide pertama → **Add selected to queue** → baris menjadi `In queue`.
    4. `/keywords` memuat ide itu.
  - **Pemeriksaan:** tidak ada permintaan ke host luar, dan `fake.requests` berisi tepat 2 `POST /v1/messages`.
  - Screenshot laporan (`deviceScaleFactor: 2`) disimpan ke `$SMOKE_SCREENSHOT_DIR` kalau variabel itu diset.
- [ ] **Step 2: Jalankan.** Run:
  `CHROME_SMOKE_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome .venv/bin/pytest tests/test_advisor_smoke.py -q`.
  Expected: PASS.
- [ ] **Step 3: README.** Bagian baru **"AI Advisor"** setelah bagian Catalog (bahasa Indonesia), berisi:
  - langkah membuat API key (console.anthropic.com → Settings → API Keys) dan mengisi saldo (Billing);
  - perkiraan biaya US$0,40–0,80 per analisis, dengan 5 pencarian web ≈ US$0,05;
  - batas bulanan di Settings;
  - saran memasang batas belanja di console Anthropic;
  - data yang dikirim dan yang tidak (spec §6.2);
  - cara kerja pencarian web;
  - laporan lama gratis dibuka lagi.

  `macos/README.txt` mendapat 2–3 baris ringkas. Nomor bagian berikutnya disesuaikan.
- [ ] **Step 4: Seluruh suite + paket.**
  - Run: `CHROME_SMOKE_PATH=… .venv/bin/pytest -q`. Expected: semua PASS (termasuk smoke).
  - Run: `.venv/bin/python -m tools.build_app 6.0.0`. Expected: `dist/Etsy-Insights.zip` dibuat dan memuat
    `requirements.txt` dengan baris `anthropic`.
- [ ] **Step 5: Commit.** `git commit -m "feat: advisor smoke test, README and 6.0.0 package"`
