# Etsy Marketplace Insights — Pencari Peluang Keyword

**Tanggal:** 2026-11-11
**Status:** Disetujui. **Revisi 1 (§16)** disetujui setelah rekaman kenali; §16 menggantikan bagian lain bila bertentangan.

## 1. Tujuan

Menemukan keyword/niche di Etsy yang:

- **volume pencariannya besar**,
- **conversion rate-nya tinggi**, dan
- **pesaingnya masih sedikit** (kolamnya belum ramai),

sehingga pemilik toko tahu di mana sebaiknya membuat listing baru.

Sumber data: halaman **Marketplace Insights** di Shop Manager
(`https://www.etsy.com/your/shops/me/marketplace-insights`), yang hanya bisa
diakses setelah login sebagai seller dan tidak tersedia lewat Etsy Open API.

**Kriteria sukses**

1. Setiap hari, dengan satu klik, tool menjalankan hingga 15 pencarian
   (masing-masing memanen ±130–180 keyword terkait, lihat §16) tanpa memicu
   CAPTCHA/verifikasi pada kondisi normal.
2. Anda mendapat file Excel berisi keyword yang diurutkan menurut skor
   peluang, dengan label Emas / Potensial / Lewati.
3. Akun seller tidak pernah diakses dengan cara selain browser Chrome asli
   di Mac Anda sendiri.

## 2. Keputusan yang sudah diambil

| Topik | Keputusan |
|---|---|
| Pendekatan | **A**: otomatisasi pelan di Chrome asli Anda, membaca data yang dimuat halaman sendiri. Bukan memanggil API internal langsung. |
| Sumber keyword | **Gabungan**: daftar Anda (`keywords.txt`) didahulukan, sisa kuota dipakai untuk menelusuri keyword terkait |
| Komputer | Mac + Google Chrome |
| Sambungan ke browser | **Opsi 1**: profil Chrome khusus "Etsy Riset" + Python via Chrome DevTools Protocol |
| Cara menjalankan | **Manual**: Anda klik dua kali `mulai.command` saat sedang di depan Mac |
| Penyimpanan | SQLite lokal, semua data tetap di Mac Anda |
| Hasil | File Excel |
| Strategi data | **Panen** (Revisi 1, §16): satu pencarian menyimpan keyword utama + semua keyword terkaitnya |

**Sengaja tidak dilakukan:** proxy atau rotasi IP, penyamaran fingerprint,
penembusan CAPTCHA, pemanggilan API internal Etsy secara langsung, dan sesi
paralel. Untuk akun yang sedang login, semua itu justru menaikkan risiko.

## 3. Arsitektur

```
etsy-insights/
├── setup.command        # sekali: cek Python, buat .venv, pasang library
├── mulai.command        # sesi harian (opsi: --uji, --abaikan-pendinginan)
├── kenali.command       # mode kenal-halaman: rekam data saat Anda mencari manual
├── export.command       # buat Excel terbaru
├── config.toml          # pengaturan (dengan nilai default aman)
├── keywords.txt         # daftar keyword Anda, satu per baris
├── etsy_insights/
│   ├── __main__.py      # CLI: run | kenali | export | status
│   ├── config.py        # baca config + paksa batas keras
│   ├── browser.py       # buka/sambung Chrome profil "Etsy Riset"
│   ├── pacer.py         # ritme manusia, kuota, pendinginan
│   ├── insights_page.py # navigasi, mengetik, menangkap respons, deteksi bahaya
│   ├── parser.py        # fungsi murni: data mentah -> angka (bisa dites offline)
│   ├── store.py         # SQLite: antrean, hasil, sesi
│   ├── session.py       # alur satu sesi (memakai unit-unit di atas)
│   ├── score.py         # skor peluang
│   ├── export.py        # tulis Excel
│   └── recorder.py      # mode kenal-halaman
├── tests/
├── data/etsy.db         # database (tidak masuk git)
├── hasil/               # file Excel
├── logs/                # log setiap sesi
└── rekaman/             # file rekaman dari kenali.command
```

**Batas antar-unit**

- `parser.py` tidak tahu apa-apa soal browser. Inputnya data mentah (JSON/HTML),
  outputnya `KeywordMetrics`. Semua tes parser berjalan offline.
- `session.py` hanya berhubungan dengan antarmuka `InsightsPage`
  (`open()`, `search(keyword) -> RawResult`, `check_danger() -> DangerSignal | None`).
  Di tes, antarmuka ini diganti `FakeInsightsPage`, jadi alur sesi bisa dites
  tanpa Chrome.
- `pacer.py` menerima jam dan generator acak dari luar, sehingga bisa dites
  dengan waktu dan angka acak yang dikunci.

**Library:** Python ≥ 3.11 (memakai `tomllib` bawaan), `playwright` (hanya
`connect_over_cdp`, tanpa mengunduh browser bawaan Playwright), `openpyxl`,
dan `pytest` untuk tes.

## 4. Sambungan ke Chrome

- Chrome asli dijalankan sebagai proses terpisah:
  `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
  `--user-data-dir="$HOME/Library/Application Support/EtsyRiset/chrome-profile"`
  `--remote-debugging-port=9222 --no-first-run`
- Profil terpisah ini wajib, karena Chrome 136+ menolak remote debugging pada
  profil default. Profil harian Anda tidak disentuh sama sekali.
- Kalau port 9222 sudah dipakai Chrome profil Etsy Riset, tool memakai Chrome
  itu. Kalau dipakai program lain, tool berhenti dengan pesan yang jelas
  (port bisa diubah di config).
- Script tersambung lewat `playwright.chromium.connect_over_cdp`. Karena Chrome
  tidak diluncurkan oleh Playwright, tidak ada flag `--enable-automation`,
  tidak ada banner "controlled by automated software", dan `navigator.webdriver`
  bernilai `false`.
- Login Etsy dilakukan manual oleh Anda **sekali** di profil ini. Etsy mungkin
  meminta verifikasi email karena "perangkat baru".

## 5. Alur satu sesi (`mulai.command`)

1. **Cek awal**
   - Baca `config.toml` dan paksa batas keras (lihat §6).
   - Sinkronkan `keywords.txt` ke antrean: keyword baru masuk sebagai
     `source=user, depth=0`. Kalau keyword itu sudah ada sebagai keyword
     terkait, statusnya dinaikkan menjadi keyword Anda.
   - Kalau kuota hari ini (tanggal lokal Mac) habis, atau sedang dalam masa
     pendinginan, tool menjelaskan alasannya lalu keluar.
2. **Buka Chrome** (§4). Buka Shop Manager dulu
   (`https://www.etsy.com/your/shops/me/dashboard`), tunggu 3–8 detik, lalu
   masuk ke Marketplace Insights dengan mengklik menunya. Kalau ternyata belum login, tool berhenti
   dan meminta Anda login manual. Ini tidak dihitung sebagai tanda bahaya.
3. **Untuk setiap keyword dari antrean** (urutan di §7):
   1. Tandai `in_progress`.
   2. Klik kotak pencarian (posisi klik sedikit diacak), kosongkan, lalu ketik
      per huruf dengan jeda 60–180 ms. Ada peluang 10% untuk jeda "ragu"
      300–900 ms. Lalu tekan Enter.
   3. Tangkap respons JSON yang dimuat halaman untuk pencarian itu
      (`page.on("response")`, disaring dengan pola URL dari rekaman kenali).
      Kalau tidak ada respons yang cocok, data dibaca dari tampilan halaman.
   4. Periksa tanda bahaya (§8).
   5. "Membaca" hasil selama 5–15 detik, dengan peluang 50% scroll pelan.
   6. Simpan hasil, termasuk **data mentah**, supaya bisa diurai ulang kalau
      parser diperbaiki tanpa mengecek ulang ke Etsy.
   7. Simpan hasil panen keyword terkait (lihat §16.2), kedalaman maksimal 2.
   8. Jeda 20–60 detik. Setiap 8–12 keyword, istirahat 2–5 menit.
4. **Berhenti** saat salah satu terjadi: kuota tercapai, durasi sesi habis,
   ada tanda bahaya, 3 kegagalan berturut-turut, Ctrl+C, atau Chrome ditutup.
5. **Ringkasan** di terminal: jumlah keyword yang dicek, keyword baru yang
   ditemukan, sisa antrean, sisa kuota hari ini, dan alasan berhenti.
   Chrome dibiarkan terbuka.

**Mode `--uji`:** sama persis, tetapi hanya 3 keyword. Dipakai untuk uji coba
nyata pertama.

## 6. Pengaturan & batas keras

| Pengaturan (`config.toml`) | Default | Batas keras (tidak bisa dilewati) |
|---|---|---|
| `kuota_harian` | 15 pencarian | maks 30 |
| `durasi_sesi_menit` | 45 | maks 60 |
| `jeda_antar_keyword_detik` | 20–60 | batas bawah min 15 |
| `istirahat_setiap` | 8–12 keyword | — |
| `istirahat_detik` | 120–300 | — |
| `kecepatan_ketik_ms` | 60–180 | batas bawah min 40 |
| `waktu_baca_detik` | 5–15 | batas bawah min 3 |
| `keyword_terkait_maks` | 200 (per pencarian) | — |
| `kedalaman_maks` | 2 | maks 3 |
| `cek_ulang_setelah_hari` | 30 | min 7 |
| `pendinginan_jam` | 24 | min 12 |
| `volume_minimum` | 100 | — |
| `bobot` | volume 0.40, conversion 0.35, kompetisi 0.25 | dinormalisasi agar totalnya 1 |
| `port_debug` | 9222 | — |

Kalau nilai di config melewati batas keras, tool memakai batas kerasnya dan
menampilkan peringatan. Semua angka acak diambil secara seragam di dalam
rentangnya.

**Yang dihitung ke kuota:** setiap keyword yang sudah diketik dan di-Enter,
apa pun hasilnya (berhasil, `no_data`, atau gagal). Kuota direset menurut
tanggal lokal Mac. Durasi sesi sudah termasuk jeda dan istirahat. Kalau
durasi habis saat sebuah keyword sedang diproses, keyword itu diselesaikan
dulu baru sesi berhenti.

## 7. Data & antrean

**Tabel `keywords`:** `id`, `keyword` (unik; dinormalisasi: huruf kecil,
spasi dirapikan), `source` (`user` | `related`), `parent_id`, `depth`,
`status` (`pending` | `in_progress` | `done` | `no_data` | `failed`),
`added_at`, `last_checked_at`, `fail_count`.

**Tabel `results`:** `id`, `keyword_id`, `checked_at`, `search_volume`,
`conversion_rate`, `competition_value`, `competition_kind` (`count` |
`level`), `trend_json`, `related_json`, `raw_json`, `parser_version`.

**Tabel `sessions`:** `id`, `started_at`, `ended_at`, `checked_count`,
`stop_reason`, `cooldown_until`.

**Urutan antrean:**
1. `pending` dengan `source=user`, yang lebih lama ditambahkan lebih dulu.
2. `pending` dengan `source=related`, kedalaman terkecil dulu, lalu urutan
   ditambahkan.
3. Terakhir, keyword `done`/`no_data` yang `last_checked_at`-nya lebih tua
   dari `cek_ulang_setelah_hari`. Ini hanya jika semua yang `pending` sudah
   habis.

**Saat mulai sesi**, keyword yang tertinggal di status `in_progress` (karena
sesi sebelumnya terputus) dikembalikan ke `pending`. Keyword yang gagal 3
kali di sesi berbeda menjadi `failed` dan tidak dicoba lagi otomatis.

## 8. Tanda bahaya & penanganan error

| Situasi | Tindakan | Pendinginan |
|---|---|---|
| CAPTCHA, iframe captcha, halaman "verify you're human"/"unusual activity" | Berhenti seketika, tanpa mencoba ulang | Ya, 24 jam |
| Dialihkan ke halaman login di tengah sesi | Berhenti seketika | Ya, 24 jam |
| HTTP 403/429 pada dokumen utama atau respons Insights | Berhenti seketika | Ya, 24 jam |
| Data tidak terbaca (tampilan Etsy berubah) | Hitung sebagai gagal; setelah 3 berturut-turut berhenti dengan pesan "jalankan `kenali.command` lagi" | Tidak |
| Halaman lambat atau internet putus (> 60 detik) | Keyword kembali ke antrean, dihitung gagal | Tidak |
| Keyword tanpa data (volume terlalu kecil) | Status `no_data`, bukan error | Tidak |
| Ctrl+C atau Chrome ditutup | Berhenti rapi; keyword yang sedang diproses kembali ke `pending` | Tidak |

Teks dan selector untuk mendeteksi CAPTCHA/verifikasi dimulai dari daftar umum,
lalu dilengkapi dari rekaman kenali. Pendinginan bisa dilewati dengan
`mulai.command --abaikan-pendinginan`, setelah Anda mengetik `YA` sebagai
konfirmasi.

Semua kejadian ditulis ke `logs/sesi-YYYYMMDD-HHMMSS.log`.

## 9. Mode kenal-halaman (`kenali.command`)

Tujuannya agar parser ditulis dari data asli, bukan tebakan.

1. Membuka/menyambung Chrome profil Etsy Riset dan membuka Marketplace Insights.
2. **Tidak mengotomatisasi apa pun.** Anda sendiri yang mencari 2–3 keyword.
3. Merekam: URL, status, dan isi setiap respons JSON dari `etsy.com`, URL
   halaman, serta snapshot HTML dan screenshot setiap kali Anda menekan Enter
   di terminal.
4. Saat Anda mengetik `selesai`, rekaman disimpan ke
   `rekaman/kenali-YYYYMMDD-HHMM.json`. Nilai dari kunci JSON yang namanya
   mengandung `csrf`, `token`, `email`, `session`, `cookie`, `password`,
   `secret`, `auth`, `phone`, atau `address` (tidak peka huruf besar/kecil)
   diganti `"[DIHAPUS]"`.
   Header request dan cookie tidak direkam sama sekali.
5. File itu Anda kirim ke Claude. Dari situ dibuat: pola URL respons yang
   ditangkap, `parser.py`, selector kotak pencarian, menu navigasi, dan tanda
   bahaya. Data rekaman yang sudah dibersihkan juga dipakai sebagai fixture tes.

## 10. Skor peluang

Dihitung dari **hasil terbaru** setiap keyword yang **layak**, yaitu volume ≥
`volume_minimum` dan ketiga metrik ada.

- `p_volume` = persentil volume di antara keyword yang layak (0–100;
  nilai seri mendapat persentil rata-rata).
- `p_conversion` = persentil conversion rate.
- `p_kompetisi_rendah` = 100 − persentil kompetisi. Kalau kompetisi berupa
  level (misalnya Low/Medium/High), level dipetakan ke 1/2/3 sebelum dirank.

```
skor = 0.40 × p_volume + 0.35 × p_conversion + 0.25 × p_kompetisi_rendah
```

**Label**

- **Emas:** `p_volume ≥ 66.7` dan `p_conversion ≥ 66.7` dan
  `p_kompetisi_rendah ≥ 66.7`.
- **Potensial:** bukan Emas dan `skor ≥ 60`.
- **Lewati:** sisanya.
- **Data kurang:** tidak layak dirank. Hanya muncul di sheet "Semua data".

Kalau keyword yang layak masih kurang dari 10, Excel menampilkan catatan
bahwa peringkat masih kasar karena datanya sedikit.

**Pencarian per listing** = volume ÷ jumlah listing pesaing. Hanya dihitung
kalau kompetisi berupa angka (`competition_kind = count`).

## 11. Excel (`export.command`)

File: `hasil/peluang-YYYY-MM-DD.xlsx`

| Sheet | Isi |
|---|---|
| **Peluang** | Keyword, volume, conversion rate, kompetisi, pencarian per listing, skor, label, tren (kalau ada), asal keyword ("daftar Anda" atau "terkait dari: X"), tanggal cek. Diurutkan dari skor tertinggi. Baris header dibekukan, autofilter aktif, label diberi warna (Emas kuning, Potensial hijau muda, Lewati abu-abu). |
| **Semua data** | Seluruh hasil (termasuk riwayat cek ulang dan "Data kurang") dengan angka mentah |
| **Antrean** | Keyword `pending` beserta sumber dan kedalamannya |

## 12. Pengujian

**Tes otomatis (`pytest`, tanpa internet dan tanpa akun Etsy)**

- `parser`: fixture dari rekaman kenali yang sudah dibersihkan, mencakup
  keyword normal, keyword tanpa data, dan data rusak.
- `pacer`: jam palsu + seed acak tetap. Rentang jeda dipatuhi, kuota per
  tanggal lokal, pendinginan, dan batas keras config.
- `store`: database sementara. Normalisasi dan deduplikasi keyword, urutan
  antrean, pemulihan `in_progress`, aturan `failed` setelah 3 kali.
- `session`: `FakeInsightsPage` mensimulasikan sukses, tanpa data, CAPTCHA,
  403, 3 kegagalan beruntun, dan Ctrl+C. Tes memastikan alasan berhenti,
  pendinginan, dan status antrean benar.
- `score`: data contoh dengan hasil yang sudah dihitung manual, termasuk
  nilai seri, level kompetisi, dan keyword yang tidak layak.
- `export`: file Excel terbentuk dengan sheet, urutan, dan kolom yang benar.

**Uji coba nyata (oleh Anda):** `mulai.command --uji` dengan 3 keyword. Anda
melaporkan hasil terminal dan file Excel-nya.

## 13. Tahapan pengerjaan

1. **Tahap 1, fondasi + kenali:** `setup.command`, `browser.py`,
   `recorder.py`, `kenali.command`, ditambah `config`, `store`, `pacer`,
   `score`, `export`, dan `session` dengan `FakeInsightsPage` beserta tesnya.
   Anda menerima paket ini, login sekali, lalu menjalankan `kenali.command`.
2. **Tahap 2, parser dari rekaman:** dari rekaman + screenshot Anda dibuat
   `parser.py`, selector di `insights_page.py`, dan daftar tanda bahaya.
   Bobot/kolom skor disesuaikan dengan metrik yang benar-benar ada.
3. **Tahap 3, uji coba nyata:** `mulai.command --uji`, perbaikan kalau perlu,
   lalu sesi penuh.

**Pengiriman:** kode dikirim ke Anda sebagai file zip (atau repo GitHub kalau
Anda lebih suka).

## 14. Ketergantungan & risiko yang tersisa

- **Metrik yang tersedia di halaman Insights belum terkonfirmasi.** Spec ini
  mengasumsikan ada volume pencarian, conversion rate, dan ukuran kompetisi.
  Kalau salah satunya tidak ada, `score.py` secara otomatis membagi bobot
  metrik itu secara proporsional ke metrik yang tersisa. Apakah metrik
  pengganti perlu diambil dari sumber lain (misalnya jumlah pesaing dari
  Etsy Open API resmi, lihat §15) diputuskan bersama Anda di Tahap 2.
- **Ketentuan Etsy melarang akses otomatis.** Desain ini menekan risiko
  (pelan, volume kecil, browser asli, berhenti saat ada tanda bahaya), tetapi
  tidak bisa menghilangkannya. Akun seller Anda yang menanggung risikonya.
- **Koneksi DevTools** secara teori bisa dideteksi oleh sistem anti-bot yang
  canggih. Ini diterima sebagai harga untuk input keyboard yang asli.
- **Etsy bisa mengubah halaman kapan saja.** Kalau itu terjadi, tool berhenti
  dengan aman lalu meminta Anda menjalankan `kenali.command` lagi.
- **Persentil bersifat relatif** terhadap keyword yang sudah terkumpul.
  Skor sebuah keyword bisa berubah saat data bertambah.

## 15. Di luar cakupan versi 1

- Jadwal otomatis (launchd). Bisa ditambahkan setelah beberapa minggu lancar.
- Modul Etsy Open API untuk jumlah listing pesaing. Hanya dibuat kalau di
  Tahap 2 terbukti Insights tidak menyediakannya.
- Dashboard web, multi-akun, multi-toko, Windows, dan browser selain Chrome.

## 16. Revisi 1: setelah rekaman kenali (2026-11-11)

Disetujui pengguna. Bagian ini **menggantikan** isi bagian lain bila bertentangan.

### 16.1 Temuan dari rekaman

Satu pencarian di Marketplace Insights memuat data berikut, semuanya lewat respons
JSON yang dimuat halaman itu sendiri:

| Respons (path berakhiran) | Isi yang dipakai |
|---|---|
| `/marketplace-insights/results-data?query=<kw>` | `stats.searchVolume` (pencarian 30 hari), `stats.avgTotalListings` (jumlah listing pesaing, di layar disebut "Search results"), `stats.cvr` (level konversi 0–4), `stats.queryCvr` (rasio konversi sebagai pecahan), `dailyStats.stats[].searchVolume` (30 titik harian), `wowData.value` (perubahan minggu-ke-minggu dalam %), `quotaData` (`totalQuota`, `remainingQuota`, `lowRemainingQuotaThreshold`), `isQuotaReached`, `isSearchAllowed` |
| `/llm-exploratory-keywords/search/poll` (dengan `status = success`) atau `/search/enqueue` (dengan `cachedData`) | 130–180 keyword terkait. Setiap keyword berisi `searchTerm`, `searchVolume`, `avgTotalListings`, dan `cvr` (level 0–4). Daftar ini dibuat asinkron: enqueue, lalu poll berulang sampai `status = success` (±2–8 detik). |
| `/chart-series-data` | Isinya sama dengan `dailyStats`, jadi tidak dipakai |

- **Level konversi Etsy:** 0 = Very low, 1 = Low, 2 = Typical, 3 = High, 4 = Very high. Arti ini dicocokkan dengan screenshot.
- **Keyword tanpa data** (misalnya salah ketik "swearshirt") berisi `searchVolume = 0` dan `cvr = null`, lalu dicatat sebagai `no_data`.
- **Kotak pencarian** di halaman hasil: `input[aria-label="Input to search for keywords"]`.
- **Menu Shop Manager:** `a[data-app-key="marketplace-insights"]`.
- **URL hasil:** `/your/shops/me/marketplace-insights/search?query=<kw>…`.

### 16.2 Strategi panen

- Setiap pencarian menyimpan dua hal:
  - **hasil cari** untuk keyword itu (data lengkap + tren), dan
  - **hasil panen** untuk setiap keyword terkait (volume, pesaing, level konversi), maksimal `keyword_terkait_maks` (default 200) per pencarian.
- Keyword hasil panen berstatus `harvested`. Datanya sudah ada, jadi ikut dirank tanpa perlu dicari satu per satu.
- Panen hanya disimpan sampai kedalaman `kedalaman_maks`. Sebuah keyword hanya dicari kalau kedalamannya < `kedalaman_maks`.
- Kalau keyword yang sama muncul lagi di daftar lain, data panennya memperbarui baris yang sama (tidak menumpuk). Hasil cari selalu ditambahkan sebagai riwayat.

### 16.3 Urutan pencarian (menggantikan §7 "Urutan antrean")

1. Keyword dari `keywords.txt` yang belum dicari, dari yang paling lama ditambahkan.
2. Keyword `harvested` dengan skor peluang tertinggi, yang belum pernah dicari dan kedalamannya < `kedalaman_maks`.
3. Keyword yang terakhir dicari lebih dari `cek_ulang_setelah_hari` lalu, yang paling lama lebih dulu. Ini hanya kalau nomor 1 dan 2 kosong.

### 16.4 Kuota & tanda berhenti tambahan

- `kuota_harian` default **15 pencarian**, dengan batas keras **30**.
- **Kuota Etsy.** Tool berhenti seketika dengan alasan `kuota_etsy` (tanpa pendinginan) kalau:
  - `isQuotaReached = true`, atau
  - `isSearchAllowed = false`, atau
  - `remainingQuota ≤ lowRemainingQuotaThreshold`.

  Sesi berikutnya pada hari yang sama ditolak.
- **Jeda antar-sesi.** Jeda minimum juga berlaku antar-sesi: kalau sesi sebelumnya berakhir belum lama, tool menunggu sisa jeda acak sebelum pencarian pertama.
- **Timeout.** Pencarian dianggap gagal kalau `results-data` untuk keyword itu tidak datang dalam 30 detik. Daftar keyword terkait ditunggu paling lama 20 detik tambahan. Kalau tidak datang, hasil utama tetap disimpan.

### 16.5 Skor (menggantikan sebagian §10)

- `p_conversion` dihitung dari **level konversi 0–4**, karena level ini tersedia untuk semua keyword. `queryCvr` hanya disimpan dan ditampilkan.
- Kompetisi selalu berupa jumlah listing (`count`), jadi "pencarian per listing" selalu tersedia.

### 16.6 Excel (menambah §11)

- **Kolom "Konversi"** menampilkan level dalam Bahasa Indonesia: Sangat rendah, Rendah, Biasa, Tinggi, Sangat tinggi.
- **Kolom "Rasio konversi"** (persen) diisi kalau keyword itu pernah dicari langsung.
- **Asal keyword:** "daftar Anda", "panen dari: X", atau "dicari".
- **Kolom "Tren"** memakai perubahan minggu-ke-minggu dari Etsy (misalnya "+22.7%"), kalau ada.
- **Sel teks** yang diawali `=`, `+`, `-`, atau `@` disimpan sebagai teks (bukan rumus), dan karakter kontrol dibuang.
- **Status** di sheet "Semua data" ditulis dalam Bahasa Indonesia.

### 16.7 Isi Tahap 2

- `parser.py`.
- `insights_page.py`: implementasi `InsightsPage` yang asli, termasuk deteksi bahaya.
- `planner.py`: urutan pencarian sesuai §16.3.
- Perubahan di `store`, `session`, `score`, dan `export`.
- Perintah `run`:
  - `--uji` menjalankan 3 pencarian;
  - `--abaikan-pendinginan` meminta konfirmasi `YA`.
- Log ke `logs/`.
- Kunci agar tidak ada dua sesi yang berjalan bersamaan.
- `mulai.command`.
- Perekam kenali juga menyensor token berbentuk JWT di mana pun.

### 16.8 Profil selera (disetujui pengguna, masuk Tahap 2)

Untuk setiap keyword yang **dicari langsung**, profil selera diambil dari data yang sudah dimuat
di respons `results-data`, yaitu `competitiveResearchListingCards.listingCards` (±20 listing
teratas) dan `competitivePriceData.searchTermMedianPrice`. Tidak ada pencarian atau unduhan
tambahan. Keyword hasil panen tidak punya profil.

- **Tema populer:** kata dan frasa dua kata yang muncul di ≥ 2 judul listing teratas, dihitung per judul. Kata umum dan kata dari keyword itu sendiri dibuang. Maksimal 10.
- **Harga dibayar pembeli:** `medianPriceLow`–`medianPriceHigh`. **Harga listing teratas:** harga termurah–termahal di kartu listing.
- **Kekuatan pemain teratas:** median ulasan, % Bestseller, % Star Seller, jumlah toko berbeda.
- **Kesulitan masuk:**
  - **Sulit:** median ulasan ≥ 2.000, atau (Bestseller ≥ 80% dan median ulasan ≥ 1.000).
  - **Mudah:** median ulasan < 300 dan Bestseller < 50%.
  - **Sedang:** selain itu.
  - Hanya ditampilkan, tidak memengaruhi skor.
- **5 contoh listing teratas:** judul, harga, ulasan, dan link.
- **Excel:**
  - sheet baru **"Selera"**, satu baris per keyword yang dicari;
  - kolom tambahan *Harga pasar* dan *Kesulitan masuk* di sheet Peluang.
- **Di luar cakupan:** analisis gambar dan ringkasan yang ditulis AI.
