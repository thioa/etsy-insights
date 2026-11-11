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
4. **Pembukaan pertama:** klik kanan **Etsy Insights** → **Open** → **Open**. Ini perlu karena
   aplikasinya tidak ditandatangani Apple. Di macOS terbaru, kalau tetap ditolak:
   *System Settings → Privacy & Security → Open Anyway*.
5. **Saat pertama dibuka**, aplikasi akan:
   - **menyiapkan dirinya sendiri** (sekali, 1–2 menit; muncul notifikasi "Setting up Etsy Insights…");
   - **menawarkan impor data lama.** Klik **Choose folder…**, lalu pilih folder `etsy-insights`
     lama Anda (misalnya `Downloads/etsy-insights`). Database, `keywords.txt`, dan rekaman akan
     disalin. `config.toml` lama sengaja tidak disalin, karena kuota defaultnya sudah berubah.
6. **Browser terbuka** ke `http://127.0.0.1:8765/`. Itulah aplikasinya.

## 2. Pemakaian sehari-hari

- **Buka Etsy Insights** dari Applications atau Dock. Kalau aplikasinya sudah menyala, yang terbuka
  hanya tab baru.
- **Session:**
  - **Test run (3 searches)** untuk uji coba, **Start session** untuk sesi harian (default 15 pencarian).
  - Progres, keyword yang sedang dicari, dan catatan langkahnya diperbarui otomatis.
  - **Stop** menghentikan sesi dengan rapi.
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

## 3. Kalau sesi berhenti

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

## 4. Letak data

- **Data aplikasi:** `~/Library/Application Support/Etsy Insights/` (database, `keywords.txt`,
  `config.toml`, log, rekaman). Saat memperbarui aplikasi, cukup ganti file .app-nya; data tetap aman.
- **File Excel:** *Documents → Etsy Insights*.

## 5. Cadangan lewat Terminal

Semua perintah lama tetap ada, dan memakai data yang sama dengan aplikasi:

```bash
"/Applications/Etsy Insights.app/Contents/MacOS/etsy-insights" --cli run --uji
```

Perintah lain: `--cli run`, `--cli status`, `--cli export`, `--cli kenali` (mode rekam).

## 6. Risiko yang perlu Anda ketahui

- **Ketentuan Etsy melarang akses otomatis.** Desain alat ini menekan risikonya: pelan, volume kecil,
  Chrome asli dari IP Anda sendiri, dan langsung berhenti saat ada tanda bahaya. Tetapi risikonya
  tidak bisa dihilangkan sepenuhnya, dan akun seller Anda yang menanggungnya.
- Etsy bisa mengubah halamannya kapan saja. Kalau itu terjadi, alat ini berhenti dengan aman.
- Aplikasi web hanya bisa dibuka dari Mac ini (`127.0.0.1`), dan setiap tombol dilindungi kode
  rahasia, sehingga situs lain di browser Anda tidak bisa memicu sesi.
