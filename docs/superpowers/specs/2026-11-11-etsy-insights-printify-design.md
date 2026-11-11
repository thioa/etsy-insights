# Etsy Insights — Koneksi Printify (Tahap 4)

**Tanggal:** 2026-11-11
**Status:** Desain disetujui per bagian, menunggu review spec
**Dasar:** `2026-11-11-etsy-insights-scraper-design.md` (termasuk §16) dan
`2026-11-11-etsy-insights-web-app-design.md`. Semua aturan keamanan sesi Etsy di sana tetap berlaku
tanpa perubahan. Tahap ini tidak mengubah apa pun di sisi Etsy.
**Sumber fakta API:** https://developers.printify.com/ dan https://developers.printify.com/openapi.json
(dibaca 2026-11-11).

## 1. Tujuan

Listing pengguna bergantung pada produk Printify (print-on-demand). Tahap ini menghubungkan
Etsy Insights dengan Printify supaya:

- **A. Peluang tersaring dan berharga.** Setiap keyword peluang dicocokkan ke jenis produk
  Printify, lalu dihitung perkiraan margin per penjualan. Keyword yang layak diberi label
  **Ready to sell**.
- **B. Riset terarah.** Jenis produk dan tags produk Printify pengguna menjadi usulan keyword
  awal untuk antrean riset.

**Di luar tahap ini (tahap C, nanti):** membuat produk, mengunggah desain, publish ke Etsy, pesanan,
dan webhook.

**Kriteria sukses**

- Setelah menempelkan token dan menekan **Sync now**, pengguna melihat jenis produknya dengan biaya
  asli dalam beberapa menit.
- Opportunities bisa disaring ke **Ready to sell**, dan setiap baris menunjukkan produk dan margin.
- Hitungan margin sama dengan hitungan manual (contoh di §8).
- Usulan keyword bisa masuk antrean dengan dua klik (centang, lalu **Add selected**).
- Aplikasi tidak pernah menulis apa pun ke Printify, dan perilaku sesi Etsy tidak berubah.

## 2. Keputusan

| Hal | Keputusan |
|---|---|
| Cakupan | A + B. C ditunda. |
| Sumber produk | Produk di toko Printify pengguna (*own*) + jenis produk yang dipilih dari katalog (*picked*) |
| Cara koneksi | API resmi Printify dengan personal access token, hanya membaca |
| Izin token | `shops.read`, `products.read`, `catalog.read` |
| Sinkronisasi | Manual lewat tombol **Sync now** |
| Pasar dan ongkir | Mayoritas pembeli dari AS, gratis ongkir (ongkir Printify mengurangi margin) |
| Mata uang | USD. Harga yang dibayar pembeli dari Marketplace Insights sudah dalam USD |
| Biaya produksi | Varian aktif termurah dari jenis produk itu |
| Fee Etsy | Pengaturan, default 9,5% + US$0,45 per penjualan |
| Batas Ready to sell | Margin ≥ US$5 per penjualan (pengaturan) |
| Usulan keyword | Hanya masuk antrean setelah pengguna klik **Add** |

## 3. Istilah (teks UI, bahasa Inggris)

| Istilah UI | Arti |
|---|---|
| Printify | Menu dan halaman baru |
| Product type | Satu produk katalog + satu print provider, misalnya "Unisex Heavy Blend Crewneck Sweatshirt · Monster Digital" |
| Your product / Picked | Asal jenis produk: dari toko pengguna / dipilih dari katalog |
| Product words | Kata yang membuat keyword cocok dengan jenis produk |
| Cost from | Biaya produksi varian aktif termurah |
| US shipping | Ongkir item pertama ke AS |
| Est. margin | Perkiraan margin per penjualan (USD dan %) |
| Ready to sell | Label untuk keyword yang memenuhi §8.4 |
| No match | Tidak ada jenis produk yang cocok |
| Search to see price | Keyword belum punya harga yang dibayar pembeli |
| Cost unknown | Jenis produk *Picked* tanpa biaya manual |
| No US shipping | Printify tidak mencantumkan ongkir ke AS |
| No longer available | Jenis produk *Picked* sudah tidak ada di katalog |
| Price needed for a $5 margin | Harga jual terendah agar margin minimum tercapai |
| Suggested keywords | Usulan keyword awal dari Printify |

## 4. Arsitektur

Semua bagian baru adalah modul terpisah dengan satu tugas jelas. Web server tetap satu proses.

| Modul | Tugas |
|---|---|
| `etsy_insights/printify_api.py` | Klien HTTP baca-saja (stdlib `urllib`): header, jeda antar permintaan, coba ulang, pemetaan error |
| `etsy_insights/printify_sync.py` | Menjalankan sync: mengambil data, menormalkan, lalu menyerahkan hasil ke store dalam satu langkah |
| `etsy_insights/product_words.py` | Kamus kata produk bawaan, normalisasi, dan pencocokan keyword ↔ jenis produk |
| `etsy_insights/margin.py` | Hitungan margin, harga minimal, dan status per keyword (dalam sen, bilangan bulat) |
| `etsy_insights/printify_store.py` | Tabel dan query Printify di `etsy.db` (koneksi dari `Store`) |
| `etsy_insights/printify_token.py` | Menyimpan, membaca, dan menghapus token |
| `etsy_insights/web/printify.py` | Halaman dan API Printify (blueprint baru) |

**Alur sync:** pengguna klik **Sync now** → `POST /api/printify/sync` → thread latar di web server
menjalankan `printify_sync.run(...)` dengan kunci (hanya satu sync sekaligus). Progres disimpan di
memori dan dibaca lewat `GET /api/printify/status`. Database baru ditulis di akhir dalam satu
transaksi. Kalau server berhenti di tengah sync, tidak ada yang tertulis.

**Kecepatan:** pencocokan dan margin dihitung saat halaman dibuka. Kalau Opportunities menjadi lebih
lambat dari 0,5 detik tambahan pada 30 ribu keyword, hasilnya dicache dengan pola yang sama seperti
antrean di `/api/status`. Kuncinya `Store.change_stamp()`, versi data Printify, dan config.

**Sisi Etsy tidak tersentuh.** Sync tidak memakai Chrome, sesi, kuota, atau kunci sesi. Sync boleh
berjalan saat sesi riset berjalan (WAL; tabel berbeda; satu transaksi singkat di akhir).

## 5. Koneksi ke Printify

**Token**

- Disimpan di `APP_HOME/printify-token` dengan izin file `0600`, ditulis secara atomik
  (file sementara lalu rename).
- Disimpan hanya setelah **Test connection** berhasil (`GET /v1/shops.json`).
- Tidak pernah dikirim balik ke browser, ditulis ke log, Excel, atau rekaman. UI hanya
  menampilkan 4 karakter terakhir.
- **Disconnect** menghapus file token. Data hasil sync tetap ada dan tetap dipakai untuk margin.

**Permintaan HTTP**

- Base URL `https://api.printify.com`. Header `Authorization: Bearer <token>` dan
  `User-Agent: EtsyInsights/4.0`.
- Jeda minimal **1 detik** antar permintaan (≤ 60 per menit, di bawah batas katalog 100 per menit).
- Timeout 30 detik per permintaan.
- **429:** tunggu sesuai `Retry-After` (default 60 detik), coba ulang maksimal 3 kali.
- **5xx atau jaringan putus:** coba ulang setelah 5, 15, lalu 45 detik. Setelah itu berhenti.
- **401:** token ditolak. **403:** izin kurang, dan pesannya menyebut izin yang dibutuhkan endpoint itu.
- Hanya metode `GET`.

**Endpoint yang dipakai**

| Endpoint | Untuk |
|---|---|
| `GET /v1/shops.json` | Test connection dan memilih toko |
| `GET /v1/shops/{shop_id}/products.json?page=N&limit=50` | Produk pengguna, per halaman sampai habis |
| `GET /v1/catalog/blueprints.json` | Nama jenis produk dan pencarian katalog |
| `GET /v1/catalog/blueprints/{id}/print_providers.json` | Nama print provider per jenis produk |
| `GET /v1/catalog/blueprints/{id}/print_providers/{pp}/shipping.json` | Ongkir dan waktu produksi |

**Langkah sync**

1. **Toko.** Dipakai toko yang tersimpan. Kalau belum ada: toko dengan `sales_channel` `etsy` kalau
   hanya ada satu. Kalau tidak ada atau lebih dari satu, sync berhenti dan halaman meminta pengguna
   memilih toko.
2. **Produk.** Semua halaman produk toko itu. Per produk diambil `id`, `title`, `tags`, `blueprint_id`,
   `print_provider_id`, dan varian (`id`, `cost`, `is_enabled`). Produk tanpa varian aktif
   dilewati.
3. **Katalog.** `blueprints.json` sekali per sync (`id`, `title`, `brand`, `model`).
4. **Per jenis produk** (*own* dan *picked*): satu permintaan nama provider per blueprint, dan
   satu permintaan ongkir per jenis produk.
5. **Simpan** semuanya dalam satu transaksi (§6).

**Ongkir ke AS:** dari profil ongkir yang negaranya berisi `US`. Kalau tidak ada, pakai profil
`REST_OF_THE_WORLD`. Kalau keduanya tidak ada → *No US shipping*.

- Untuk *own*: profil yang memuat ID varian termurah.
- Untuk *picked*: `first_item.cost` terkecil di antara profil yang berlaku untuk AS.
- `cost` ongkir dianggap sen USD (contoh dokumentasi: 450 = US$4.50). Kalau `currency` bukan
  `USD`, ongkir dianggap tidak diketahui.

**Format tak terduga:** kalau respons tidak berbentuk seperti dokumentasi (field wajib hilang atau
tipe salah), sync berhenti. Aplikasi lalu menyimpan rekaman respons ke
`APP_HOME/rekaman/printify-YYYYMMDD-HHMMSS.json`, tanpa header dan tanpa token. Pesannya
menyebut file itu supaya bisa dikirim ke Claude.

## 6. Data

Tabel baru di `etsy.db`. Dibuat dengan `CREATE TABLE IF NOT EXISTS` saat `Store` dibuka.

```sql
CREATE TABLE IF NOT EXISTS printify_meta (      -- key/value: shop_id, shop_title, last_sync_at, last_sync_error
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS printify_blueprints (  -- katalog untuk pencarian
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, brand TEXT, model TEXT
);
CREATE TABLE IF NOT EXISTS printify_types (
    id INTEGER PRIMARY KEY,
    blueprint_id INTEGER NOT NULL,
    print_provider_id INTEGER NOT NULL,
    title TEXT NOT NULL,                 -- nama blueprint
    provider_title TEXT,
    source TEXT NOT NULL,                -- 'own' | 'picked'
    cost_min_cents INTEGER,              -- own: dari sync; picked: manual
    cost_max_cents INTEGER,
    shipping_us_cents INTEGER,           -- NULL = No US shipping / belum diketahui
    handling_days INTEGER,
    words_json TEXT NOT NULL,            -- daftar product words
    words_edited INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 1,
    synced_at TEXT,
    UNIQUE (blueprint_id, print_provider_id)
);
CREATE TABLE IF NOT EXISTS printify_products (
    id TEXT PRIMARY KEY,                 -- ID produk Printify
    type_id INTEGER NOT NULL REFERENCES printify_types(id),
    title TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    cost_min_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS keyword_product_links (  -- tautan manual
    keyword_id INTEGER PRIMARY KEY REFERENCES keywords(id),
    type_id INTEGER NOT NULL REFERENCES printify_types(id)
);
```

**Aturan simpan sync (satu transaksi):**

- `printify_products` diganti seluruhnya dengan hasil sync.
- Jenis produk *own* dibuat atau diperbarui dari produk. Biaya = min dan max `cost` varian aktif di
  semua produk jenis itu.
- Jenis produk yang tadinya *own* tetapi tidak punya produk lagi: dihapus kalau tidak ditautkan
  manual. Kalau ditautkan, jadi *picked* dan biayanya tetap.
- Jenis produk yang ada di toko dan juga *picked* menjadi *own*. Biaya sync menggantikan biaya
  manual.
- *Picked* yang blueprint-nya tidak ada lagi di katalog atau provider-nya tidak ada lagi:
  `available = 0`.
- `words_json` hanya diisi ulang kalau `words_edited = 0`.
- `printify_blueprints` diganti seluruhnya. `printify_meta.last_sync_at` diisi. `last_sync_error`
  dikosongkan.

Sync yang gagal hanya menulis `last_sync_error`.

## 7. Pencocokan keyword ↔ jenis produk

**Normalisasi:** huruf kecil. `-`, `_`, `/`, dan `&` menjadi spasi. Tanda baca lain dibuang.
Dipecah menjadi kata. Setiap kata dibuat bentuk dasar sederhana, dalam dua langkah:

1. **Jamak:** `ies` → `ie`. Akhiran `es` dibuang untuk kata berakhiran `sses`/`xes`/`ches`/`shes`.
   Kata tunggal berakhiran -s (`canvas`, `atlas`, `bus`, `lens`, `iris`) tetap utuh, dan bentuk
   jamaknya (`canvases`) kembali ke kata itu. Selain itu, akhiran `s` dibuang kecuali untuk `ss`
   (*cases* → `case`, *vases* → `vase`).
2. **Akhiran y:** konsonan + `y` di akhir kata menjadi konsonan + `ie`.

Contoh: *hoodies*, *hoodie*, dan *hoody* → `hoodie`; *babies* dan *baby* → `babie`; *glasses* →
`glass`; *tees* → `tee`; *toys* → `toy`. Normalisasi yang sama dipakai untuk keyword dan product
words, jadi bentuk yang aneh (misalnya `canvas` → `canva`) tetap cocok di kedua sisi. Tampilan
selalu memakai teks aslinya.

**Kamus bawaan** (`product_words.DICTIONARY`). Setiap entri punya kata utama dan sinonim, misalnya:

| Kata utama | Sinonim |
|---|---|
| sweatshirt | crewneck, crew neck, jumper |
| hoodie | hooded sweatshirt, hoody |
| t shirt | tee, tshirt, shirt |
| tank top | tank |
| mug | coffee mug, cup |
| tumbler | travel mug |
| water bottle | bottle |
| tote bag | tote |
| poster | wall art, art print, print |
| canvas | canvas print |
| blanket | throw blanket |
| pillow | throw pillow, cushion |
| phone case | iphone case |
| sticker | decal |
| ornament | christmas ornament |
| hat | cap, baseball cap, trucker hat, beanie |
| baby bodysuit | onesie, baby onesie |
| socks | sock |
| notebook | journal |
| puzzle | jigsaw puzzle |
| mouse pad | mousepad |
| apron | |
| backpack | |

`shirt` hanya cocok dengan kata utuh `shirt`, tidak dengan `sweatshirt`.

**Kata produk untuk satu jenis produk:** entri kamus untuk **kata benda utama** judul blueprint,
yaitu kecocokan (kata utama atau sinonim, sebagai kata utuh) yang berakhir paling belakang di judul.
Kalau dua kecocokan berakhir di posisi yang sama, frasa terpanjang menang. Contoh: "Hooded
Sweatshirt" → *hoodie* (bukan *sweatshirt*), "Cotton Canvas Tote Bag" → *tote bag* (bukan
*canvas*). Kalau tidak ada yang cocok, daftarnya kosong.
Halaman Printify lalu menampilkan "Add product words". Pengguna bisa mengedit daftar ini
(`words_edited = 1`).

**Keyword cocok** dengan jenis produk jika urutan kata salah satu product word muncul utuh di
keyword (setelah normalisasi).

**Tautan manual** (`keyword_product_links`) menggantikan pencocokan otomatis untuk keyword itu.

**Jenis produk utama** untuk satu keyword: margin tertinggi di antara yang cocok. Kalau sama:
*own* lebih dulu, lalu biaya terendah, lalu `id` terkecil. Kalau margin belum bisa dihitung untuk
semuanya: *own* lebih dulu, lalu biaya terendah.

## 8. Margin

### 8.1 Masukan (semua dalam sen USD, bilangan bulat)

- **Harga** = titik tengah `medianPriceLow` dan `medianPriceHigh` dari hasil pencarian terbaru
  keyword itu, dibulatkan ke sen. Teks harga dibaca dari format `US$15.30` atau `$15.30`. Kalau hanya
  satu yang ada, pakai yang ada. Kalau formatnya bukan USD, statusnya *Search to see price*.
- **Biaya** = `cost_min_cents` jenis produk.
- **Ongkir** = `shipping_us_cents`.
- **Fee** = `round_half_up(harga × fee_persen / 100) + fee_tetap`.

### 8.2 Rumus

- `margin = harga − biaya − ongkir − fee`
- `margin_persen = margin / harga × 100`, satu angka desimal.
- `harga_minimal = ceil((biaya + ongkir + fee_tetap + margin_minimum) / (1 − fee_persen / 100))`,
  dalam sen.

**Contoh (harus sama persis di tes):** harga US$30.00, biaya US$12.41, ongkir US$4.75, fee 9,5% +
US$0.45.

- Fee: 285 + 45 = 330 sen.
- Margin: 3000 − 1241 − 475 − 330 = **954 sen (US$9.54, 31.8%)**.
- Harga minimal untuk margin US$5: ceil((1241 + 475 + 45 + 500) / 0.905) = ceil(2498.34) =
  **2499 sen (US$24.99)**.

### 8.3 Status per keyword (urutan pemeriksaan)

| Status | Kondisi | Teks UI |
|---|---|---|
| `no_match` | Tidak ada jenis produk yang cocok | No match |
| `no_price` | Belum dicari langsung, atau tidak ada harga USD | Search to see price |
| `cost_unknown` | Jenis produk utama tanpa biaya | Cost unknown |
| `no_shipping` | Jenis produk utama tanpa ongkir AS | No US shipping |
| `ok` | Margin terhitung | US$9.54 · 31.8% |

### 8.4 Ready to sell

Keyword diberi label **Ready to sell** jika:

- labelnya Gold atau Potential,
- statusnya `ok`, dan
- margin ≥ `margin_minimum_usd`.

Jenis produk *Picked* dengan `available = 0` tidak dipakai untuk margin.

## 9. Usulan keyword (Suggested keywords)

- **Dari kata produk:** untuk setiap kata utama jenis produk yang `available`, usulannya `{w}`,
  `custom {w}`, dan `personalized {w}`.
- **Dari tags produk pengguna:** tag dinormalkan (`normalize_keyword`) lalu dihitung berapa
  produk yang memakainya.
- Keyword yang sudah ada di database (status apa pun) dan duplikat dibuang.
- Urutan: tags (paling sering dulu, lalu abjad), kemudian usulan kata produk (abjad). Maksimal 100
  ditampilkan.
- **Add selected** memakai `keywords.add_keywords`. Keyword masuk sebagai keyword pengguna dan
  ditulis ke `keywords.txt`, sama seperti di My keywords.

## 10. Tampilan

**Menu:** Session · Opportunities · **Printify** · My keywords · Settings.

**Halaman Printify**

1. **Kartu koneksi**
   - *Belum terhubung:* judul "Connect Printify", kolom "Paste your Printify token", tombol
     **Test and save**, langkah singkat (Printify → My Profile → Connections → Generate token,
     centang `shops.read`, `products.read`, `catalog.read`).
   - *Terhubung:* "Connected · Shop: {nama} · token ends …{4 karakter} · Last sync: {waktu lokal}"
     atau "Never synced". Tombol **Sync now** dan **Disconnect**.
   - *Sedang sync:* "Syncing… {langkah} ({n} of {m})". Tombol Sync dinonaktifkan. Diperbarui
     setiap 2 detik dengan pola polling yang sama seperti Session.
   - *Perlu pilih toko:* daftar toko (nama dan sales channel) dengan tombol **Use this shop**.
   - *Error:* pesan dari §12 di bawah kartu.
2. **Product types** (tabel)
   - Kolom: Product type (judul · provider), Source (Your product / Picked), Product words (bisa
     diedit, dipisah koma), Cost from (atau isian biaya untuk *Picked*), US shipping, Matches (jumlah
     keyword dengan data yang cocok dengan jenis ini).
   - *Picked* punya tombol **Remove**. Yang `available = 0` diberi tanda "No longer available".
   - Simpan perubahan kata atau biaya per baris dengan **Save**.
3. **Add from catalog**
   - Kotak pencarian judul, brand, dan model atas `printify_blueprints` (tersedia setelah sync
     pertama).
   - Pilih hasil → daftar print provider (diambil langsung, satu permintaan) → isian biaya
     (opsional) → **Add**.
   - Saat **Add**, ongkir AS jenis itu langsung diambil (satu permintaan).
4. **Suggested keywords**
   - Tabel dengan centang: keyword, asal ("product word" / "tag on N products").
   - Tombol **Add selected**.

**Opportunities**

- Kolom baru **Product** (judul pendek jenis produk utama, atau *No match*) dan **Margin**:
  - hijau: ≥ minimum;
  - abu-abu: belum diketahui (teks status §8.3);
  - merah: negatif.
- Chip filter baru **Ready to sell**.
- Urutan baru: `sort=margin` (yang belum diketahui di bawah).

**Detail keyword**

- Panel **Printify**: tabel semua jenis produk yang cocok. Kolom: Product type, Cost, US shipping,
  Etsy fees, Margin, dan "Price needed for a ${min} margin". Jenis produk utama ditandai.
- **Link to product type:** dropdown semua jenis produk yang `available`, plus "Automatic". Pilihan
  disimpan lewat API.
- Status `no_price`: teks "Search to see price", plus tombol **Prioritize** kalau keyword hasil panen.

**Settings:** bagian baru **Selling on Etsy** dengan tiga isian:

| Isian | Kunci config | Default | Batas | Pesan error |
|---|---|---|---|---|
| Etsy fees (% of sale) | `fee_etsy_persen` | 9.5 | 0–30 | "Enter a percentage from 0 to 30." |
| Fixed fee per sale (US$) | `fee_etsy_tetap_usd` | 0.45 | 0–5 | "Enter an amount from 0 to 5." |
| Minimum margin (US$) | `margin_minimum_usd` | 5 | 0–100 | "Enter an amount from 0 to 100." |

Nilai di luar batas di `config.toml` dikoreksi ke default dengan peringatan, mengikuti pola
`_RANGE_OR_DEFAULT`. `render_config` menulis ketiganya dengan komentar bahasa Inggris.

**Excel:** sheet Opportunities mendapat kolom *Printify product*, *Est. margin (USD)*,
*Margin %*, dan *Ready to sell* (Yes/kosong). Kolom-kolom itu ditempatkan setelah *Entry difficulty*.

## 11. API web baru

Semua `POST` memakai perlindungan yang ada (token per peluncuran, Host, Origin). Respons tidak
pernah memuat token Printify.

| Metode dan path | Isi | Hasil |
|---|---|---|
| `GET /printify` | | Halaman |
| `POST /api/printify/token` | `{token}` | Test connection. Kalau berhasil, token disimpan, dan hasilnya berisi daftar toko |
| `POST /api/printify/test` | | Test connection dengan token tersimpan |
| `POST /api/printify/disconnect` | | Hapus token |
| `POST /api/printify/shop` | `{shop_id}` | Simpan pilihan toko |
| `POST /api/printify/sync` | | Mulai sync. 409 kalau sedang berjalan atau belum terhubung |
| `GET /api/printify/status` | | `{state, step, done, total, error, last_sync_at}` |
| `GET /api/printify/catalog?q=` | | Maksimal 30 blueprint yang cocok |
| `GET /api/printify/providers?blueprint_id=` | | Daftar provider (langsung dari Printify) |
| `POST /api/printify/types/add` | `{blueprint_id, print_provider_id, cost_usd?}` | Jenis produk *picked* baru |
| `POST /api/printify/types/update` | `{type_id, words?, cost_usd?}` | `cost_usd` hanya untuk *picked* |
| `POST /api/printify/types/remove` | `{type_id}` | Hanya *picked*. Tautan manual ke jenis itu ikut dihapus |
| `POST /api/printify/link` | `{keyword, type_id}` | Tautan manual. `type_id: null` kembali ke otomatis |
| `POST /api/printify/suggestions/add` | `{keywords: [...]}` | Tambah ke My keywords |

## 12. Penanganan error

| Situasi | Pesan / perilaku |
|---|---|
| Token ditolak (401) | "Printify rejected the token. Create a new token in Printify and paste it here." Sync berhenti, data lama tetap |
| Izin kurang (403) | "The token needs the {scope} permission. Create a new token with shops.read, products.read and catalog.read." |
| Terlalu cepat (429) setelah 3 kali coba | "Printify is busy. Try Sync again in a few minutes." |
| Jaringan atau 5xx setelah 3 kali coba | "Could not reach Printify. Check your internet connection and try again." |
| Tidak ada toko Etsy, atau lebih dari satu | Daftar toko, "Choose the Printify shop that is connected to your Etsy shop." |
| Format respons tidak terduga | "Printify sent data in an unexpected format. Sync stopped and nothing was changed. Send this file to Claude: {path}" |
| Sync diminta saat sync berjalan | 409, "A sync is already running." |
| Sync atau katalog sebelum terhubung | 409, "Connect Printify first." |
| Pencarian katalog sebelum sync pertama | "Run Sync once to search the catalog." |
| Biaya *Picked* tidak valid | "Enter an amount from 0.01 to 500." |

Semua error sync juga ditulis ke `printify_meta.last_sync_error` dan tampil di kartu koneksi.

## 13. Keamanan

- Token hanya dibaca oleh server dan dikirim hanya ke `https://api.printify.com`.
- Tes khusus memastikan token tidak muncul di HTML, JSON, log server, Excel, dan rekaman.
- Klien Printify hanya punya metode `GET`. Tahap ini tidak punya kode yang menulis ke Printify.
- Header anti-framing dan `no-referrer` yang ada berlaku juga untuk halaman Printify.
- Gambar produk Printify tidak dimuat. Tampilan hanya berisi teks.

## 14. Pengujian

Tidak ada tes yang menghubungi Printify atau Etsy.

- **Klien:** server HTTP palsu lokal (base URL bisa diganti untuk tes) dengan respons berbentuk
  seperti dokumentasi.
  - 200, 401, 403, 429 + `Retry-After`, 500, timeout, dan koneksi putus.
  - Jeda dan waktu tunggu memakai jam dan `sleep` yang disuntikkan, jadi tes tidak lambat.
- **Sync:**
  - fixture toko, produk dua halaman, katalog, provider, dan ongkir;
  - aturan §6 (own/picked, edited words, available, tautan manual);
  - kegagalan di tengah tidak mengubah data;
  - rekaman respons tak terduga tanpa token.
- **Kata produk:** normalisasi, bentuk jamak, tanda hubung, kata utuh ("shirt" ≠ "sweatshirt"),
  kata dari judul blueprint, dan tautan manual.
- **Margin:** contoh §8.2 persis, pembulatan, harga minimal, status §8.3, dan Ready to sell §8.4.
- **Usulan:** urutan, tanpa duplikat, keyword lama dibuang, maksimal 100.
- **Web:**
  - halaman Printify untuk setiap keadaan (belum terhubung, terhubung, sync, pilih toko, error);
  - token tidak bocor;
  - kolom dan filter Opportunities, panel detail;
  - validasi Settings dan `render_config`;
  - kolom Excel;
  - semua `POST` baru ditolak tanpa token aplikasi.
- **Smoke (Chromium sungguhan, Printify palsu):** tempel token → sync → Ready to sell muncul di
  Opportunities.
- **Uji nyata oleh pengguna:** **Test connection** dan satu kali **Sync now** dengan token baca-saja.

## 15. Tahapan (gambaran untuk rencana kerja)

1. `margin.py` dan `product_words.py` (logika murni)
2. `printify_store.py` (tabel dan aturan simpan) dan `printify_token.py`
3. `printify_api.py` (klien, coba ulang, error)
4. `printify_sync.py` (langkah sync, pilihan toko, rekaman)
5. Config, Settings, dan `render_config` untuk fee dan margin
6. Halaman dan API Printify
7. Opportunities, detail keyword, dan Excel
8. README, smoke test, dan paket aplikasi versi 4.0.0
