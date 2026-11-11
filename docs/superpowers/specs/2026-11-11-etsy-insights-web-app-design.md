# Etsy Insights — Web App Lokal (Tahap 3)

**Tanggal:** 2026-11-11
**Status:** Desain disetujui per bagian dan mockup disetujui, menunggu review spec
**Dasar:** `2026-11-11-etsy-insights-scraper-design.md` (termasuk §16). Semua aturan keamanan
sesi di sana tetap berlaku tanpa perubahan.
**Mockup:** https://claude.ai/artifact/3aeWGE9RQDnyyqgJhuGuv9 (Sesi, Peluang, Detail keyword)

## 1. Tujuan

Membuat Etsy Insights lebih intuitif dan lebih mudah dijalankan oleh satu orang (pemilik toko)
di Mac-nya sendiri:

1. **Dijalankan tanpa Terminal**, lewat ikon aplikasi.
2. **Hasil nyaman dilihat** di browser: filter, detail, grafik, dan foto listing.
3. **Keyword dan pengaturan dikelola dari layar.**

**Kriteria sukses**

- Setelah pemasangan pertama, pengguna tidak pernah perlu membuka Terminal.
- Satu sesi harian bisa dimulai, dipantau, dan dihentikan sepenuhnya dari browser.
- Semua aturan keamanan akun tetap sama persis dengan versi Terminal.

## 2. Keputusan

| Topik | Keputusan |
|---|---|
| Bentuk | Web app **lokal**, hanya untuk pengguna ini di Mac ini (`127.0.0.1`) |
| Teknologi | **Pendekatan A**: Python + Flask, halaman dibuat di server dengan sedikit JavaScript biasa, tanpa Node/build |
| Peluncur | **Pilihan B**: pembungkus ringan "Etsy Insights.app" yang memakai Python di Mac (dipasang sekali dari python.org) dan membuka tab browser |
| Bahasa | **Semua teks produk dalam bahasa Inggris**: web app, Excel, dialog macOS, pesan Terminal. README tetap berbahasa Indonesia. |
| Sesi | Dijalankan sebagai **proses terpisah** (`python -m etsy_insights run`), dihentikan dengan sinyal yang sama seperti Ctrl+C |
| Data | `~/Library/Application Support/Etsy Insights/`. Excel disimpan ke `~/Documents/Etsy Insights/`. |
| Cadangan | Perintah Terminal lama tetap berfungsi |

**Di luar cakupan:**
- jendela aplikasi sendiri atau ikon Dock yang menyala;
- notarisasi Apple;
- akses dari perangkat lain atau multi-pengguna;
- analisis gambar atau ringkasan oleh AI.

## 3. Istilah (bahasa Inggris)

| Konsep | Teks di UI |
|---|---|
| Menu | **Session · Opportunities · My keywords · Settings** |
| Tombol | **Start session**, **Test run (3 searches)**, **Stop**, **Download Excel**, **Prioritize**, **Add keywords**, **Remove**, **Save settings**, **Quit Etsy Insights** |
| Label skor | **Gold**, **Potential**, **Skip**, **Not enough data** |
| Level konversi (istilah Etsy) | **Very low**, **Low**, **Typical**, **High**, **Very high** |
| Kesulitan masuk | **Entry difficulty**: **Easy**, **Medium**, **Hard**, **Unknown**. Untuk keyword yang belum dicari langsung: **Not searched yet**. |
| Kolom | **Searches/month**, **Competing listings**, **Conversion**, **Conversion rate**, **Searches per listing**, **Score**, **Label**, **Week over week**, **Market price**, **Source**, **Date** |
| Asal keyword | **Your list**, **Harvested from: X**, **Searched (from: X)** |
| Status keyword | **Queued**, **Searching**, **Searched**, **No data**, **Failed**, **Harvested** |
| Selera | **Buyer taste**: **Popular themes**, **Price buyers pay**, **Top listing prices**, **Top 5 listings**, **View on Etsy** |
| Pendinginan | **Cooldown**: "Paused until …". Tautan **Ignore cooldown** meminta pengguna mengetik **YES**. |
| Sheet Excel | **Opportunities**, **Buyer taste**, **All data**, **Queue** |

**Alasan berhenti (`REASON_TEXT`), dalam bahasa Inggris:**

| Kode | Teks |
|---|---|
| `kuota_tercapai` | "Daily limit reached." Untuk uji coba: "Test run finished (3 searches)." |
| `durasi_habis` | "Session time limit reached." |
| `tanda_bahaya` | "Etsy showed a warning (captcha, verification, sign-in or 403/429). Paused for 24 hours to protect your account." |
| `gagal_beruntun` | "3 failures in a row. Etsy's page may have changed — run Recording mode and send the file to Claude." |
| `dihentikan` | "Stopped by you." |
| `chrome_ditutup` | "Chrome was closed." |
| `antrean_kosong` | "Nothing left to search. Add keywords in My keywords." |
| `belum_login` | "Not signed in to Etsy in the 'Etsy Riset' Chrome window. Sign in there, then start again." |
| `masa_pendinginan` | "Cooldown is active." |
| `kuota_habis` | "Today's searches are used up. Try again tomorrow." |
| `kuota_etsy` | "Etsy says the Marketplace Insights quota is (almost) used up. Try again tomorrow." |
| `halaman_tidak_terbuka` | "Etsy's page didn't load (slow internet?). Try again later." |
| `error` | "The session stopped because of an unexpected error. See the log." |

Kode alasan di database **tidak berubah**, jadi data lama tetap terbaca. Hanya teksnya yang
diganti. Pesan peringatan config, pesan CLI, mode kenali, dan dialog peluncur juga diterjemahkan
ke bahasa Inggris dengan nada yang sama.

## 4. Arsitektur

```
etsy_insights/
├── paths.py            # BARU: lokasi data (APP_HOME) + folder Excel
├── keywords.py         # BARU: menambah/menghapus keyword di keywords.txt + database
├── settings.py         # BARU: membaca/menulis config.toml dari formulir (lewat aturan batas keras config.py)
├── runner.py           # BARU: SessionRunner, yang menjalankan/menghentikan proses sesi dan membaca progres
├── web/
│   ├── __init__.py     # create_app(home, *, token, runner, now) -> Flask
│   ├── security.py     # pemeriksaan Host/Origin + token per peluncuran
│   ├── views.py        # halaman: Session, Opportunities, Keyword detail, My keywords, Settings
│   ├── api.py          # JSON: status sesi, mulai, berhenti, prioritaskan, keyword, pengaturan, keluar
│   ├── templates/      # Jinja2 (layout + 5 halaman), teks bahasa Inggris
│   └── static/         # app.css, app.js (polling progres, konfirmasi)
└── (modul lama: store, session, planner, parser, taste, export, ...)
macos/
└── Etsy Insights.app/  # pembungkus: Contents/Info.plist, Contents/MacOS/etsy-insights (bash),
                        # Contents/Resources/ (kode aplikasi + requirements + ikon)
```

**Batas antar-unit**

- `web` tidak pernah menjalankan Playwright. Pencarian hanya berjalan di proses sesi yang
  dijalankan oleh `runner`.
- `runner` memakai perintah CLI yang sudah ada:
  `python -m etsy_insights run [--uji] [--abaikan-pendinginan] --log-file <path>`.
  Untuk perintah ini ditambahkan opsi `--log-file` dan `--yes`. `--yes` menggantikan prompt YA
  dan hanya dipakai setelah pengguna mengetik YES di UI.
- `paths.APP_HOME` ditentukan oleh variabel lingkungan `ETSY_INSIGHTS_HOME`. Kalau tidak di-set,
  dipakai folder proyek, sehingga perilaku CLI lama tetap sama.
- Server membaca database bersamaan dengan proses sesi yang menulis. Karena itu `Store` membuka
  SQLite dalam mode **WAL** dengan `timeout=10`.

## 5. Halaman (sesuai mockup, teks bahasa Inggris)

1. **Session** `/`
   - Kartu: searches today (x/15), keywords collected, queue, dan account status (Safe / Cooldown until … / Etsy quota used up).
   - Tombol **Start session** dan **Test run (3 searches)**. Keduanya nonaktif kalau sesi berjalan, sedang cooldown, atau kuota habis. Saat cooldown ada tautan **Ignore cooldown**.
   - Panel *running* (polling `/api/status` setiap 2 detik):
     - progress bar x/limit;
     - keyword yang sedang dicari;
     - 20 baris log terakhir;
     - tombol **Stop**.
   - Kartu **Last session**: alasan berhenti dan angka-angkanya.
   - Sesi yang dimulai dari Terminal juga terdeteksi lewat `data/sesi.lock`, dan ditampilkan sebagai "A session is running (started from Terminal)" tanpa tombol Stop.
2. **Opportunities** `/opportunities`
   - Tabel dari `score_all`.
   - Filter (query string): label (multi), difficulty (multi, termasuk *Not searched yet*), konversi minimal, volume minimal, teks.
   - Urutan per kolom. 50 baris per halaman.
   - **Download Excel**: membuat file di `~/Documents/Etsy Insights/` lalu mengirimkannya ke browser.
3. **Keyword detail** `/keyword/<keyword>`
   - Angka utama dan grafik SVG 30 hari (kalau ada tren).
   - **Buyer taste** dari `build_profile`, dengan foto listing dari `imageUrl` asli Etsy (dimuat oleh browser pengguna).
   - Tabel keyword yang dipanen darinya (maks 50) dengan tombol **Prioritize**.
   - Keyword `harvested` yang belum dicari menampilkan "Buyer taste appears after this keyword is searched" dan tombol **Prioritize**.
4. **My keywords** `/keywords`
   - Textarea "one keyword per line" dan tombol **Add keywords**.
   - Daftar keyword dari `keywords.txt` beserta statusnya. Tombol **Remove** hanya ada untuk yang *Queued*.
5. **Settings** `/settings`
   - Formulir: daily searches (1–30), pause between searches min/maks (≥15 s), session length (≤60 min), score weights.
   - Setiap kolom menampilkan batasnya. Nilai di luar batas ditolak dengan pesan per kolom.
   - Bagian **Quit Etsy Insights**.

## 6. Aturan perilaku

- **Prioritize:** keyword dimasukkan ke `keywords.txt` dan dipromosikan menjadi keyword pengguna (`sync_user_keywords`, status `pending`), sehingga dicari pertama di sesi berikutnya.
- **Remove:** hanya untuk keyword pengguna berstatus `pending`. Baris di `keywords.txt` dihapus. Di database: kalau keyword itu punya baris panen, kembalikan ke `source='related'`, `depth=1`, `status='harvested'`; kalau tidak punya hasil sama sekali, barisnya dihapus. Keyword yang sudah dicari tidak bisa dihapus dari UI.
- **Settings:** disimpan ke `config.toml` dengan menulis ulang file dari templat yang sama (komentar bahasa Inggris). Nilai diperiksa lewat `load_config` sebelum disimpan; kalau ada peringatan pembatasan, formulir ditolak dan menampilkan pesannya.
- **Start:** server menjalankan pra-cek yang sama dengan sesi (cooldown, kuota harian, kuota Etsy hari ini, antrean kosong) **sebelum** proses sesi atau Chrome dibuka, lalu menampilkan alasannya kalau tidak bisa mulai.
- **Stop:** kirim SIGTERM. Kalau proses masih hidup setelah 30 detik, kirim SIGKILL. Keyword `in_progress` dipulihkan otomatis di sesi berikutnya.
- **Ignore cooldown:** dialog peringatan dengan input teks. Hanya "YES" yang diterima, lalu sesi dijalankan dengan `--abaikan-pendinginan --yes`.
- **Quit:** kalau ada sesi berjalan, minta konfirmasi lalu hentikan sesinya dulu. Setelah itu server berhenti dan menampilkan halaman "Etsy Insights has quit. Open it again from Applications."
- **Tab Chrome:** di akhir sesi, tab yang dibuka sesi ditutup supaya tidak menumpuk. Ini perbaikan temuan kecil Tahap 2.

## 7. Keamanan aplikasi

- Server hanya mendengarkan di `127.0.0.1` (port default 8765, bisa diubah di config `port_web`).
- **Header `Host`** harus `127.0.0.1:<port>` atau `localhost:<port>`; selain itu 403. Ini mencegah serangan DNS rebinding.
- **Setiap permintaan yang mengubah sesuatu** (POST) wajib:
  - header `Origin`, kalau ada, sama dengan asal aplikasi; dan
  - **token per peluncuran** (32 byte acak, dibuat saat server menyala, ditanam di `<meta>` setiap halaman) di header `X-App-Token` atau field formulir `token`.

  Tanpa keduanya: 403. Akibatnya situs lain di browser tidak bisa memulai sesi atau mengubah data.
- Tidak ada endpoint yang menjalankan perintah bebas. Argumen proses sesi dibangun dari daftar tetap.
- Foto listing dimuat langsung dari domain gambar Etsy (`i.etsystatic.com`) oleh browser. Server tidak menghubungi Etsy sama sekali.

## 8. Peluncur "Etsy Insights.app"

Bentuknya bundle macOS biasa. `Contents/MacOS/etsy-insights` adalah skrip bash.

**Alur saat ikon dibuka:**

1. **Cari Python ≥ 3.11** di `/Library/Frameworks/Python.framework/Versions/3.*/bin/python3`, `/usr/local/bin`, `/opt/homebrew/bin`, dan PATH. Kalau tidak ada, dialog `osascript` menampilkan "Etsy Insights needs Python 3.11 or newer." dengan tombol **Download Python** (membuka python.org) dan **Cancel**, lalu keluar.
2. **Cek Google Chrome.** Kalau tidak ada, dialog dengan tombol **Download Chrome**.
3. **Siapkan lingkungan.** Venv berada di `APP_HOME/venv`, dibuat atau diperbarui kalau belum ada atau kalau `requirements.txt` berubah (dicek lewat hash yang disimpan). Selama proses, muncul notifikasi "Setting up Etsy Insights (one time, 1–2 minutes)…". Kalau gagal, dialog menunjukkan lokasi log-nya.
4. **Impor data lama (sekali).** Kalau `APP_HOME/data/etsy.db` belum ada, dialog "Import data from an older etsy-insights folder?" dengan tombol **Choose folder…** / **Skip**. Yang disalin: `data/`, `keywords.txt`, `rekaman/`. `config.toml` lama tidak disalin, karena kuota defaultnya sudah berubah.
5. **Nyalakan server.** Kalau `http://127.0.0.1:8765/api/ping` belum merespons, server dijalankan di latar belakang (`nohup`), lalu ditunggu sampai merespons, paling lama 20 detik.
6. **Buka browser:** `open http://127.0.0.1:8765/`.

**Lain-lain:**
- `APP_HOME` berisi `config.toml`, `keywords.txt`, `data/`, `logs/`, `rekaman/`, `venv/`, dan `server.log`. Kode aplikasi ada di dalam bundle (`Contents/Resources/app/`), sehingga pembaruan cukup dengan mengganti file .app.
- Ikon aplikasi berupa ikon sederhana (`.icns`) yang dibuat sekali.
- Karena aplikasi tidak ditandatangani, pembukaan pertama lewat klik kanan → **Open** (atau *Privacy & Security → Open Anyway*). README menjelaskannya.

## 9. Penanganan error

| Situasi | Perilaku |
|---|---|
| Proses sesi crash | Kartu Last session menampilkan alasan `error` beserta tombol **Open log** (menampilkan isi log di halaman) |
| Server sudah menyala saat ikon dibuka lagi | Hanya membuka tab baru |
| Port 8765 dipakai program lain | Dialog: "Port 8765 is in use. Change `port_web` in Settings or quit the other program." |
| Database sedang ditulis | Pembacaan menunggu maksimal 10 detik (WAL + timeout). Kalau masih gagal, halaman menampilkan "Busy, try again in a moment." |
| Polling status gagal (server mati) | Banner "Etsy Insights is not running. Open it again from Applications." |

## 10. Pengujian

**Tes otomatis**

- `web` (Flask test client):
  - setiap halaman tampil dengan data contoh dari fixture;
  - POST tanpa token, dengan Host salah, atau dengan Origin asing menghasilkan 403;
  - filter/urutan/halaman di Opportunities;
  - Prioritize, Add, dan Remove;
  - Settings menolak nilai di luar batas;
  - Start ditolak saat cooldown, kuota habis, atau antrean kosong.
- `runner`:
  - memakai perintah palsu (skrip Python kecil yang menulis log dan menunggu SIGTERM);
  - start/stop, deteksi lock dari Terminal, SIGKILL setelah batas waktu (memakai waktu tunggu tes yang pendek);
  - parsing progres dari log.
- `keywords`/`settings`: berkas sementara.
- CLI `--log-file` dan `--yes`.
- Teks: semua `REASON_TEXT` dan header Excel dalam bahasa Inggris (tes yang ada diperbarui).
- Peluncur: `bash -n`, plus tes fungsi pencarian Python dan pembuatan venv dengan direktori palsu (yang bisa diuji di Linux).

**Smoke:** server dinyalakan sungguhan di port acak, lalu `/api/ping`, halaman Session, dan alur Start→Stop dicoba dengan perintah sesi palsu.

**Uji coba nyata (oleh pengguna):** pasang app, buka, Test run, Stop di tengah, lalu Download Excel.

## 11. Tahapan

1. Fondasi: `paths`, `Store` WAL, opsi CLI `--log-file`/`--yes`, teks bahasa Inggris, penutupan tab Chrome di akhir sesi.
2. `keywords`, `settings`, dan `runner`.
3. Web: keamanan, API, halaman, dan CSS/JS sesuai mockup.
4. Peluncur `.app` beserta README dan paket.
