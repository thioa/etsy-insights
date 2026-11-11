# Etsy Insights — Katalog Printify (Tahap 5)

**Tanggal:** 2026-11-11
**Status:** Desain disetujui per bagian, menunggu review spec
**Dasar:** `2026-11-11-etsy-insights-printify-design.md` (Tahap 4, termasuk perbaikan 4.0.1/4.0.2) dan
spec sebelumnya. Semua aturan keamanan sesi Etsy tetap berlaku tanpa perubahan. Sisi Printify tetap
**hanya membaca**.

## 1. Tujuan

Pengguna ingin satu tempat untuk:

- **menjelajah semua produk yang bisa dibuat Printify** (lebih dari 1.000 model), dikelompokkan per
  kategori, dengan foto; dan
- **melihat peluang Etsy per kategori**, lalu meminta riset untuk kategori yang menarik.

**Di luar tahap ini:** AI advisor (rekomendasi produk dan tema, usulan keyword dari katalog) menjadi
Tahap 6 dan dibangun di atas data tahap ini.

**Kriteria sukses**

- Setelah **Sync now**, menu **Catalog** menampilkan semua kategori dengan foto, jumlah model, dan
  ringkasan peluang Etsy.
- Satu klik **Research** memasukkan keyword awal kategori ke antrean, tanpa mengubah kuota harian.
- Dari halaman kategori, sebuah model bisa ditambahkan ke Product types (provider, ongkir, biaya), lalu
  keyword kategori itu langsung mendapat kolom Product dan Margin.
- Halaman Catalog untuk 30 ribu keyword dan sekitar 50 kategori terbuka dalam waktu kurang dari 1 detik.

## 2. Keputusan

| Hal | Keputusan |
|---|---|
| Tujuan | Menjelajah + peluang (pilihan C) |
| Pendekatan | Katalog per kategori (pendekatan A) |
| Riset kategori | Atas permintaan lewat tombol **Research** (3 keyword awal), bukan otomatis |
| Foto | Ditampilkan, dimuat langsung dari server gambar Printify |
| Kategori | Dibentuk dari kata benda utama judul produk dengan kamus kata produk |
| Detail per produk | Provider dan ongkir diambil saat dibutuhkan, lalu disimpan 30 hari |
| Biaya produksi | Tetap diisi manual untuk produk yang belum pernah dibuat (Printify tidak membagikannya) |

## 3. Istilah (teks UI, bahasa Inggris)

| Istilah UI | Arti |
|---|---|
| Catalog | Menu dan halaman baru |
| Printify catalog | Judul halaman Catalog |
| Category | Kelompok model dengan kata benda utama yang sama, misalnya *Necklaces* |
| Not researched yet / Harvested only / Researched | Status riset kategori (§6) |
| Keywords with data | Jumlah keyword berdata di kategori itu |
| Most searched | Keyword dengan volume pencarian tertinggi |
| Opportunities | Jumlah keyword Gold dan Potential |
| Ready to sell | Jumlah keyword berlabel Ready to sell (Tahap 4) |
| Research | Tombol yang memasukkan 3 keyword awal ke antrean |
| In queue: N keywords / Researched | Keadaan tombol Research |
| In my products | Model atau kategori yang sudah ada di Product types |
| Choose provider | Membuka pilihan print provider untuk sebuah model |
| Add to my product types | Menambahkan model sebagai jenis produk *Picked* |

## 4. Arsitektur

| Bagian | Perubahan |
|---|---|
| `etsy_insights/product_words.py` | Kamus diperluas (§5). Fungsi baru `category_for(title)`, `CATEGORY_NAMES`, `category_slug()` |
| `etsy_insights/printify_store.py` | Kolom `image_url` di `printify_blueprints`; tabel cache provider dan ongkir (§7) |
| `etsy_insights/printify_sync.py` | Menyimpan foto pertama (`https`) setiap blueprint |
| `etsy_insights/catalog.py` (baru) | Menyusun kategori dari blueprint, ringkasan peluang, status dan keyword awal Research |
| `etsy_insights/web/catalog.py` (baru) | Halaman Catalog dan halaman kategori, API Research dan ongkir |
| `etsy_insights/web/printify.py` | `providers` dan `types/add` memakai cache §7 |

Semua perhitungan kategori dilakukan saat halaman dibuka. Tidak ada tabel kategori: kategori adalah hasil
fungsi dari judul blueprint dan kamus.

## 5. Kamus dan kategori

**Kamus diperluas** dari 23 menjadi 52 entri. Semua entri Tahap 4 tetap ada; tambahannya, dalam urutan
ini:

| Kata utama | Sinonim |
|---|---|
| necklace | pendant, name necklace |
| bracelet | bangle, charm bracelet |
| earrings | earring |
| keychain | key chain, keyring, key ring |
| candle | |
| coaster | |
| wall clock | clock |
| rug | area rug |
| towel | beach towel, hand towel, tea towel |
| shower curtain | |
| doormat | door mat, welcome mat |
| tapestry | wall tapestry |
| flag | garden flag |
| cutting board | chopping board, charcuterie board |
| sweatpants | joggers, jogger |
| leggings | |
| polo | polo shirt |
| long sleeve shirt | long sleeve tee, long sleeve t shirt |
| bib | baby bib |
| pet bandana | dog bandana |
| pet bowl | dog bowl, cat bowl |
| pet bed | dog bed, cat bed |
| laptop sleeve | laptop case |
| wallet | |
| greeting card | birthday card, christmas card, thank you card |
| postcard | |
| calendar | |
| wine glass | |
| can cooler | koozie, can koozie |

Sengaja tidak dimasukkan: *shorts* (bentuk dasarnya `short` akan cocok dengan *short sleeve*) dan *card*
sendirian (akan cocok dengan *card holder*).

**`category_for(title) -> str`** = kata utama entri hasil `words_for_title(title)` (kata benda utama,
aturan Tahap 4 §7), atau `"other"` kalau tidak ada yang cocok.

**`CATEGORY_NAMES`**: nama tampilan bahasa Inggris untuk setiap kata utama, bentuk jamak dengan huruf
besar di awal: *Sweatshirts, Hoodies, T-shirts, Tank tops, Mugs, Tumblers, Water bottles, Tote bags,
Posters, Canvas prints, Blankets, Pillows, Phone cases, Stickers, Ornaments, Hats, Baby bodysuits, Socks,
Notebooks, Puzzles, Mouse pads, Aprons, Backpacks, Necklaces, Bracelets, Earrings, Keychains, Candles,
Coasters, Wall clocks, Rugs, Towels, Shower curtains, Doormats, Tapestries, Flags, Cutting boards,
Sweatpants, Leggings, Polo shirts, Long sleeve shirts, Bibs, Pet bandanas, Pet bowls, Pet beds, Laptop
sleeves, Wallets, Greeting cards, Postcards, Calendars, Wine glasses, Can coolers*. Ditambah
`"other"` → *Other*.

**`category_slug(main)`** = kata utama dengan spasi diganti `-` (misalnya `wall-clock`). Alamat
halaman: `/catalog/<slug>`.

**Dampak pada Tahap 4:** kamus yang lebih luas juga berlaku untuk Product types dan Opportunities. Kata
produk jenis produk yang sudah ada diperbarui pada Sync berikutnya, kecuali yang pernah diedit pengguna.

## 6. Ringkasan peluang dan Research

**Keyword milik kategori:** setiap keyword yang punya hasil (`store.latest_results()`) dan mengandung
salah satu kata entri kategori itu (kata utama atau sinonim), dengan pencocokan Tahap 4 §7. Satu keyword
boleh masuk lebih dari satu kategori. Pencocokan memakai indeks frasa yang sama seperti
`product_fit._Matcher`.

**Ringkasan per kategori** (`CategorySummary`):

| Field | Isi |
|---|---|
| `keywords` | Jumlah keyword milik kategori |
| `searched` | Jumlah di antaranya yang dicari langsung (punya hasil `kind = 'search'`) |
| `status` | `not_researched` (0 keyword), `harvested_only` (ada keyword, 0 dicari langsung), `researched` |
| `most_searched` | `(keyword, volume)` dengan volume tertinggi, atau kosong |
| `gold`, `potential` | Jumlah label Gold dan Potential di antara keyword yang layak dinilai |
| `best` | `(keyword, skor, label)` dengan skor tertinggi, atau kosong |
| `ready` | Jumlah keyword dengan `ProductFit.ready` (Tahap 4); `None` kalau kategori tidak punya jenis produk dengan biaya |
| `models` | Jumlah blueprint di kategori itu |
| `in_my_products` | Benar kalau ada jenis produk (*own*/*picked*, `available`) dengan kategori yang sama |

**Urutan "Best opportunities" (default):**
1. `gold + potential` terbanyak;
2. skor `best` tertinggi;
3. kategori dengan data (`keywords > 0`) sebelum yang belum;
4. nama.

*Other* selalu terakhir. Urutan lain: *Most searched* (volume `most_searched`), *Most products*
(`models`), *Name*.

**Research** (`research_seeds(main) = [main, f"custom {main}", f"personalized {main}"]`):
- Seed **perlu diriset** kalau belum ada di database, atau ada tetapi berstatus `harvested` (hasil panen
  yang belum pernah dicari langsung).
- `POST /api/catalog/research {category}` mengirim seed yang perlu diriset ke `keywords.add_keywords`.
  Keyword itu masuk sebagai keyword pengguna dan ditulis ke `keywords.txt`. Keyword hasil panen ikut
  dipindah ke depan antrean, sama seperti tombol Prioritize.
- **Status tombol:**
  - *Research*: ada seed yang perlu diriset;
  - *In queue: N keywords*: tidak ada seed yang perlu diriset, dan N di antaranya masih `pending` atau
    `in_progress`;
  - *Researched*: semua seed sudah dicari langsung. Tombol tidak bisa diklik.
- Research untuk *Other* tidak tersedia.
- Catatan di dekat tombol: *"Uses up to 3 of your daily searches."*
- Research tidak mengubah kuota, jeda, atau aturan sesi apa pun.

## 7. Data dan Sync

**`printify_blueprints`** mendapat kolom `image_url TEXT`, ditambahkan dengan `ALTER TABLE` kalau belum
ada, sama seperti migrasi `results`. `Blueprint` mendapat field `image_url: str = ""`.

**Sync** menyimpan `image_url` = alamat pertama di `images` yang berupa string dan diawali `https://`,
atau `""`. Katalog dari Sync lama (tanpa foto) tetap tampil dengan *No photo*.

**Cache detail** (tabel baru):

```sql
CREATE TABLE IF NOT EXISTS printify_catalog_providers (
    blueprint_id INTEGER NOT NULL, provider_id INTEGER NOT NULL, title TEXT NOT NULL,
    fetched_at TEXT NOT NULL, PRIMARY KEY (blueprint_id, provider_id)
);
CREATE TABLE IF NOT EXISTS printify_catalog_shipping (
    blueprint_id INTEGER NOT NULL, provider_id INTEGER NOT NULL, shipping_us_cents INTEGER,
    handling_days INTEGER, fetched_at TEXT NOT NULL, PRIMARY KEY (blueprint_id, provider_id)
);
```

- **Masa berlaku cache: 30 hari.** Setelah itu, data diambil ulang saat dibutuhkan. Hasil yang
  `shipping_us_cents IS NULL` (*No US shipping*) juga disimpan.
- `GET /api/printify/providers` (Tahap 4) memakai cache provider.
- `POST /api/printify/types/add` memakai kedua cache.
- Kalau Printify gagal, tidak ada yang disimpan dan pesannya sama seperti Tahap 4 §12.

## 8. Tampilan

**Menu:** Session · Opportunities · **Catalog** · Printify · My keywords · Settings.

**`GET /catalog`**
- **Judul:** *Printify catalog*, dengan keterangan *"Everything Printify can make, grouped by product.
  See where Etsy demand is."*
- **Tanpa katalog** (`has_blueprints()` salah): *"Connect Printify and run Sync to load the catalog."*
  dengan tautan ke `/printify`.
- **Katalog tanpa foto sama sekali:** catatan *"Run Sync to load product photos."*
- **Baris alat** (parameter URL, tanpa JavaScript):
  - `q`: mencocokkan nama kategori dan judul, brand, atau model blueprint;
  - `sort`: `best | searched | products | name`;
  - chip `status=researched|not_researched` dan `mine=1`.
- **Kartu kategori:**
  - foto model pertama yang punya foto, nama kategori, dan *"N products"*;
  - lencana status;
  - *Most searched: keyword · 12,400/mo* atau *—*;
  - *Opportunities: 3 Gold · 5 Potential*;
  - *Ready to sell: N* (kalau `ready` bukan `None`);
  - tombol Research (§6) dan **View products**.

**`GET /catalog/<slug>`**
- **Ringkasan:** kartu angka (*Keywords with data*, *Most searched*, *Opportunities*, *Ready to sell*)
  dan tombol Research.
- **Top keywords:**
  - 10 keyword dengan skor tertinggi di kategori ini;
  - kolom: keyword (tautan ke detail), Searches/month, Competing listings, Conversion, Label, Margin;
  - tautan *See all in Opportunities* ke `/opportunities?q=<kata utama>`.
- **Products:** kisi semua model di kategori ini, diurutkan menurut judul. Setiap kartu berisi:
  - foto (`loading="lazy"`, `alt` = judul) atau *No photo*;
  - judul, serta brand dan model;
  - lencana *In my products* kalau model itu sudah ada di Product types;
  - **Choose provider**, yang membuka pilihan provider (dari `/api/printify/providers`). Setelah provider
    dipilih, ongkir ke AS dan waktu produksi diambil dari `GET /api/catalog/shipping?blueprint_id=&provider_id=`
    (wajib `X-App-Token`, memakai cache). Lalu isian biaya dan **Add to my product types**
    (`/api/printify/types/add`).
- **Slug tidak dikenal:** halaman *"Unknown category."* dengan tautan ke `/catalog`, status 404.

**Foto:** hanya `image_url` yang diawali `https://`. Header `Referrer-Policy: no-referrer` (Tahap 3) berlaku.

## 9. Penanganan error

| Situasi | Perilaku |
|---|---|
| Belum terhubung atau belum Sync | Pesan dan tautan ke halaman Printify |
| Katalog lama tanpa foto | *No photo* dan *"Run Sync to load product photos."* |
| Gagal mengambil provider atau ongkir | Pesan Tahap 4 §12 (atau pesan sertifikat 4.0.1) di bawah kartu produk; tidak ada yang tersimpan |
| Provider tidak mengirim ke AS | *No US shipping*; produk tetap bisa ditambahkan |
| Research untuk kategori yang sudah *Researched* | 409 *"Already researched."* |
| Research untuk *Other* atau kategori tidak dikenal | 404 *"Unknown category."* |
| `/api/catalog/shipping` tanpa `X-App-Token` | 403 |

## 10. Keamanan

- `POST /api/catalog/research` memakai perlindungan yang ada (token aplikasi, Host, Origin).
  `GET /api/catalog/shipping` dan `/api/printify/providers` wajib `X-App-Token`, karena memanggil
  Printify dengan token pengguna.
- Token Printify tidak pernah dikirim ke browser.
- Judul, brand, model, dan alamat gambar dari Printify selalu di-escape. Alamat selain `https://`
  dibuang.
- Klien Printify tetap hanya `GET`.

## 11. Pengujian

Tidak ada tes yang menghubungi Printify atau Etsy.

- **Kategori:**
  - sekitar 40 judul bergaya katalog Printify (pakaian, perhiasan, rumah, minuman, aksesori, hewan,
    alat tulis), dengan kata benda utama yang menang;
  - *Other* untuk judul yang tidak dikenal;
  - `category_slug`;
  - `CATEGORY_NAMES` lengkap untuk semua entri kamus.
- **Ringkasan:** status, `most_searched`, Gold/Potential, `best`, `ready`, `in_my_products`, urutan
  default dan urutan lain.
- **Research:** seed, seed yang sudah ada dilewati, `keywords.txt`, status *In queue*/*Researched*,
  409 dan 404.
- **Sync:** `image_url` tersimpan, alamat selain `https` dibuang, migrasi kolom pada database lama.
- **Cache:** provider dan ongkir tidak diminta dua kali dalam 30 hari, diminta ulang setelah 30 hari,
  dan tidak disimpan saat Printify gagal.
- **Web:**
  - Catalog (tanpa katalog, dengan katalog, `q`, `sort`, chip filter);
  - halaman kategori dan slug tidak dikenal;
  - `X-App-Token` wajib;
  - judul berisi `<script>` tetap aman.
- **Kecepatan:** ringkasan semua kategori untuk 30 ribu keyword dan 52 kategori < 0,5 detik (pengukuran,
  bukan tes otomatis).
- **Smoke (Chromium sungguhan, Printify palsu, foto dari server lokal):** Catalog → Research → kategori →
  Choose provider → Add → model muncul di Product types; tidak ada permintaan ke host luar.

## 12. Tahapan (gambaran untuk rencana kerja)

1. Kamus diperluas, `category_for`, `CATEGORY_NAMES`, `category_slug`
2. `image_url` (migrasi, Sync) dan tabel cache provider/ongkir
3. `catalog.py`: kategori dari blueprint, ringkasan, Research
4. API: Research, ongkir; `providers` dan `types/add` memakai cache
5. Halaman Catalog dan kategori, menu, JS, CSS
6. Smoke test, README, paket 5.0.0
