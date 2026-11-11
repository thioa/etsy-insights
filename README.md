# Etsy Insights: Pencari Peluang Keyword

Etsy Insights mencari keyword Etsy dengan **volume pencarian besar**, **konversi tinggi**, dan
**pesaing sedikit**, lalu menunjukkan **selera pembeli** untuk setiap keyword.

Datanya dibaca dari halaman Marketplace Insights di Shop Manager Anda sendiri, lewat Chrome asli
di Mac Anda, dengan jeda yang pelan dan aman. Semua data tersimpan di Mac Anda.

Tampilan aplikasinya berbahasa Inggris; README ini berbahasa Indonesia.

## 1. Pemasangan (sekali saja)

1. **Pasang Python 3.11 atau lebih baru**, kalau belum ada. Unduh dari
   https://www.python.org/downloads/macos/ (installer *macOS 64-bit universal2*).
2. **Pastikan Google Chrome** ada di folder Applications.
3. **Unzip `Etsy-Insights.zip`**, lalu seret **Etsy Insights.app** ke folder **Applications**.
   Kalau mau, seret juga ke Dock.
4. **Pembukaan pertama.** Aplikasinya tidak ditandatangani Apple, jadi macOS akan menolaknya dengan
   pesan *"Etsy Insights" Not Opened*. Klik **Done** (jangan *Move to Trash*), lalu pilih salah satu:
   - *System Settings → Privacy & Security* → scroll ke bagian **Security** → **Open Anyway** →
     masukkan password → **Open Anyway** lagi. Kalau tombolnya tidak ada, buka aplikasinya sekali
     lagi, lalu kembali ke halaman itu.
   - Atau satu perintah di Terminal:
     `xattr -dr com.apple.quarantine "/Applications/Etsy Insights.app"`

   Ini cukup sekali. Di macOS 15 (Sequoia) ke atas, klik kanan → Open sudah tidak bisa melewati
   penolakan ini.
5. **Saat pertama dibuka**, aplikasi akan:
   - **menyiapkan dirinya sendiri** (sekali, 1–2 menit; muncul notifikasi "Setting up Etsy Insights…");
   - **menawarkan impor data lama.** Klik **Choose folder…**, lalu pilih folder `etsy-insights`
     lama Anda (misalnya `Downloads/etsy-insights`), yaitu folder yang berisi folder `data`.
     - Yang disalin: database, `keywords.txt`, dan rekaman. `config.toml` lama sengaja tidak
       disalin, karena kuota defaultnya sudah berubah.
     - Kalau folder yang dipilih salah, aplikasi akan bilang dan bertanya lagi.
     - Kalau macOS meminta izin membuka folder Downloads, klik **Allow**.
   - **Setelah impor, jangan pakai folder lama lagi.** `mulai.command` dan file `.command` lain di
     folder lama punya batas harian dan cooldown sendiri. Kalau dipakai bersamaan dengan aplikasi,
     jumlah pencarian Anda bisa dobel, dan itu bisa membuat Etsy curiga. Folder lama boleh dihapus.
6. **Browser terbuka** ke `http://127.0.0.1:8765/`. Itulah aplikasinya.

## 2. Pemakaian sehari-hari

- **Buka Etsy Insights** dari Applications atau Dock. Kalau aplikasinya sudah menyala, yang terbuka
  hanya tab baru.
- **Session:**
  - **Test run (3 searches)** untuk uji coba, **Start session** untuk sesi harian (default 15 pencarian).
  - Progres, keyword yang sedang dicari, dan catatan langkahnya diperbarui otomatis.
  - **Stop** menghentikan sesi dengan rapi.
  - Kalau sesi gagal dimulai (misalnya Chrome tidak ditemukan), pesannya muncul di kartu
    *Last session*. **Open log** menampilkan catatan lengkapnya.
  - Selama sesi berjalan, jendela Chrome "Etsy Riset" jangan diklik dan jangan di-minimize.
- **Opportunities:**
  - Tabel peluang dengan filter label (*Gold / Potential / Skip*), *Entry difficulty*, konversi,
    volume, dan pencarian teks.
  - Klik sebuah keyword untuk melihat grafik 30 hari, *Buyer taste* (tema populer, harga yang
    dibayar pembeli, kesulitan masuk), dan 5 listing teratas beserta fotonya.
  - **Prioritize** membuat keyword hasil panen dicari pertama di sesi berikutnya.
  - **Download Excel** mengunduh file Excel (juga disimpan di *Documents → Etsy Insights*).
- **My keywords:** tambah keyword (satu per baris), atau hapus keyword yang masih *Queued*.
- **Settings:** kuota harian (1–30), jeda, durasi sesi, dan bobot skor. Tombol
  **Quit Etsy Insights** ada di halaman ini.

## 3. Printify: produk dan margin

Etsy Insights bisa membaca produk Printify Anda untuk menjawab dua pertanyaan: **keyword ini bisa saya
jual dengan produk apa**, dan **berapa sisa uang saya per penjualan**. Aplikasi **hanya membaca**
dari Printify; tidak bisa mengubah, membuat, atau mem-publish apa pun di toko Printify Anda.

**Menghubungkan (sekali saja)**

1. Di Printify, buka **My Profile → Connections** dan buat *personal access token*.
2. Centang **hanya** tiga izin ini: `shops.read`, `products.read`, `catalog.read`.
3. Di Etsy Insights, buka menu **Printify**, tempel token, lalu klik **Test and save**.
   Token disimpan di Mac Anda saja dan tidak ditampilkan lagi. Token Printify berlaku 1 tahun.
4. Klik **Sync now**. Aplikasi membaca produk Anda, biaya produksinya, dan ongkir ke AS.
   Kalau akun Anda punya lebih dari satu toko, pilih toko yang terhubung ke Etsy.

Klik **Sync now** lagi kapan saja kalau Anda menambah produk atau Printify mengubah harga.

**Membaca hasilnya**

- Di **Opportunities**, kolom **Product** menunjukkan produk Printify yang cocok, dan **Margin**
  menunjukkan perkiraan sisa uang per penjualan:
  harga yang dibayar pembeli − biaya produksi − ongkir ke AS (gratis ongkir) − fee Etsy.
  - Hijau: di atas margin minimum Anda. Kuning: untung tipis. Merah: rugi.
  - *Search to see price*: harga pembeli baru diketahui setelah keyword itu dicari. Klik
    **Prioritize** di halaman keyword supaya dicari di sesi berikutnya.
  - *No match*: tidak ada produk yang cocok. Di halaman keyword, Anda bisa menautkannya sendiri lewat
    **Link to product type**.
- Centang **Ready to sell** untuk melihat keyword berlabel Gold/Potential yang produknya ada dan
  marginnya di atas batas minimum.
- Halaman keyword menampilkan rincian biaya dan **harga jual minimal** untuk mencapai margin minimum.

**Produk yang belum pernah Anda buat**

Di **Add from catalog**, cari produk Printify (misalnya "tumbler" atau "Gildan 18000"), pilih print
provider, lalu isi biaya produksinya sendiri. Printify tidak membagikan biaya produk yang belum Anda
buat. Biaya itu bisa dilihat di Printify saat membuat produk.

**Kata produk.** Sebuah keyword cocok dengan produk kalau mengandung salah satu *product words*-nya
(misalnya *sweatshirt, crewneck*). Kata ini dibuat otomatis dan bisa Anda ubah di tabel Product types.

**Suggested keywords.** Usulan keyword dari tags produk Anda dan jenis produknya. Centang yang Anda
mau, lalu klik **Add selected** untuk memasukkannya ke antrean riset.

**Fee Etsy.** Default-nya 9,5% + US$0,45 per penjualan, dengan margin minimum US$5. Cocokkan dengan
fee di Shop Manager Anda (Finances), lalu ubah di **Settings → Selling on Etsy**.

## 4. Catalog: semua produk Printify

Menu **Catalog** menampilkan semua produk yang bisa dibuat Printify (lebih dari seribu model),
dikelompokkan per kategori seperti *T-shirts*, *Mugs*, atau *Necklaces*. Katalog dan fotonya ikut
terunduh saat Anda menekan **Sync now** di halaman Printify. Fotonya dimuat langsung dari server
gambar Printify.

**Membaca kartu kategori**
- **Status riset:**
  - *Not researched yet*: belum ada keyword sama sekali;
  - *Harvested only*: hanya ada keyword hasil panen, harga pembeli belum diketahui;
  - *Researched*: sudah ada keyword yang dicari langsung.
- **Most searched:** keyword dengan pencarian terbanyak di kategori itu.
- **Opportunities:** jumlah keyword Gold dan Potential.
- **Ready to sell:** muncul kalau kategori itu sudah punya produk di Product types beserta biayanya.

Urutan default *Best opportunities* menaruh kategori dengan peluang terbanyak di atas. Gunakan kotak
pencarian dan filter (*Researched*, *Not researched yet*, *In my products*) untuk menyaring.

**Tombol Research**
- Memasukkan 3 keyword awal kategori ke depan antrean, misalnya *necklace*, *custom necklace*, dan
  *personalized necklace*.
- Memakai kuota harian biasa (paling banyak 3 pencarian). Tidak ada aturan keamanan sesi yang berubah.
- Setelah diklik, kartu menampilkan *In queue*, lalu *Researched* setelah ketiganya dicari.

**Menambahkan produk dari halaman kategori**
1. Klik **View products** pada kartu kategori.
2. Pada model yang Anda mau, klik **Choose provider** lalu pilih print provider. Ongkir ke AS dan waktu
   produksi muncul otomatis.
3. Isi biaya produksi (lihat di Printify saat membuat produk), lalu klik **Add to my product types**.

Setelah itu, keyword di kategori itu mendapat kolom Product dan Margin di Opportunities. Data provider
dan ongkir disimpan 30 hari, jadi membuka produk yang sama tidak meminta ke Printify lagi.

## 5. Kalau sesi berhenti

| Pesan | Artinya | Yang perlu dilakukan |
|---|---|---|
| *Daily limit reached* | Kuota hari ini habis | Lanjut besok |
| *Test run finished (3 searches)* | Uji coba selesai | Lihat hasilnya di Opportunities |
| *Etsy showed a warning … Paused for 24 hours* | CAPTCHA, verifikasi, login, atau 403/429 | Selesaikan verifikasi di Chrome "Etsy Riset". Tunggu cooldown 24 jam. |
| *Etsy says the Marketplace Insights quota is (almost) used up* | Kuota Insights dari Etsy | Lanjut besok |
| *3 failures in a row* | Tampilan Etsy mungkin berubah | Kabari Claude |
| *Not signed in to Etsy …* | Chrome "Etsy Riset" keluar dari akun | Login di Chrome itu, lalu mulai lagi |
| *Nothing left to search* | Antrean kosong | Tambah keyword di My keywords |

Cooldown **bisa** dilewati lewat tautan *Ignore cooldown* (Anda harus mengetik `YES`), tetapi
itu **tidak disarankan**.

## 6. Letak data

- **Data aplikasi:** `~/Library/Application Support/Etsy Insights/` (database, `keywords.txt`,
  `config.toml`, log, rekaman).
- **Memperbarui aplikasi:** klik **Quit Etsy Insights** di Settings dulu, lalu ganti file .app-nya.
  Data tetap aman.
- **File Excel:** *Documents → Etsy Insights* (`opportunities-TANGGAL.xlsx`).

## 7. Cadangan lewat Terminal

Perintah Terminal tetap ada lewat aplikasinya. Perintah ini memakai data yang sama dengan aplikasi
(bukan data di folder lama):

```bash
"/Applications/Etsy Insights.app/Contents/MacOS/etsy-insights" --cli run --uji
```

Perintah lain: `--cli run`, `--cli status`, `--cli export`, `--cli kenali` (mode rekam).

## 8. Risiko yang perlu Anda ketahui

- **Ketentuan Etsy melarang akses otomatis.** Desain alat ini menekan risikonya: pelan, volume kecil,
  Chrome asli dari IP Anda sendiri, dan langsung berhenti saat ada tanda bahaya. Tetapi risikonya
  tidak bisa dihilangkan sepenuhnya, dan akun seller Anda yang menanggungnya.
- Etsy bisa mengubah halamannya kapan saja. Kalau itu terjadi, alat ini berhenti dengan aman.
- Aplikasi web hanya bisa dibuka dari Mac ini (`127.0.0.1`), dan setiap tombol dilindungi kode
  rahasia, sehingga situs lain di browser Anda tidak bisa memicu sesi.
