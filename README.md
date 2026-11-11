# Etsy Insights: Pencari Peluang Keyword

Alat ini mencari keyword Etsy dengan **volume pencarian besar**, **konversi tinggi**,
dan **pesaing sedikit**. Datanya dibaca dari halaman Marketplace Insights di Shop Manager Anda
sendiri, lewat Chrome asli di Mac Anda. Semua data tersimpan di Mac Anda.

Setiap pencarian menyimpan data keyword itu **dan memanen 130–180 keyword terkait** beserta
volume, jumlah pesaing, dan level konversinya. Karena itu cukup 15 pencarian per hari.

## 1. Pemasangan (sekali saja)

1. Unzip, lalu pindahkan folder `etsy-insights` ke tempat yang mudah ditemukan.
   Kalau sudah punya folder versi lama, timpa saja file-filenya. Data di `data/` tetap aman.
2. Buka **Terminal**, lalu masuk ke folder itu, misalnya:
   ```bash
   cd ~/Downloads/etsy-insights
   ```
3. Pasang:
   ```bash
   bash setup.command
   ```

## 2. Daftar keyword Anda

Isi `keywords.txt`, satu keyword per baris. Contoh:

```
personalized cutting board
custom pet portrait
```

Keyword dari daftar ini selalu dicari lebih dulu. Setelah daftar habis, alat ini otomatis
mencari keyword hasil panen yang skornya paling tinggi.

## 3. Uji coba pertama (3 pencarian)

```bash
bash mulai.command --uji
```

Chrome "Etsy Riset" terbuka sendiri. Biarkan saja dan jangan dipakai selama sesi berjalan.
Terminal menampilkan setiap langkah dan diakhiri ringkasan. Kirim ringkasan itu ke Claude
kalau ada yang aneh.

## 4. Sesi harian

```bash
bash mulai.command
```

- Default **15 pencarian per hari**, dengan jeda acak 20–60 detik dan sesekali istirahat
  2–5 menit. Durasinya kira-kira 15–25 menit.
- Jalankan saat Anda sedang di depan Mac. Untuk berhenti di tengah jalan, tekan **Ctrl+C**.
  Data yang sudah terkumpul tetap tersimpan.
- Log setiap sesi tersimpan di folder `logs/`.

**Alasan sesi berhenti:**

| Pesan | Artinya | Yang perlu dilakukan |
|---|---|---|
| Kuota tercapai | 15 pencarian hari ini sudah habis | Lanjut besok |
| Tanda bahaya (CAPTCHA/verifikasi/login/403/429) | Etsy curiga atau meminta verifikasi | Selesaikan verifikasi di Chrome. Alat ini berhenti **24 jam** (masa pendinginan). |
| Kuota Etsy | Etsy menandai kuota Insights hampir habis | Lanjut besok |
| 3 kegagalan berturut-turut | Tampilan Etsy mungkin berubah | Jalankan `bash kenali.command` lagi dan kirim rekamannya ke Claude |
| Belum login | Chrome "Etsy Riset" keluar dari akun | Login manual di Chrome itu, lalu jalankan lagi |

Masa pendinginan **bisa** dilewati dengan `bash mulai.command --abaikan-pendinginan`
(Anda harus mengetik `YA`), tetapi itu **tidak disarankan**.

## 5. Hasil Excel

```bash
bash export.command
```

File `hasil/peluang-YYYY-MM-DD.xlsx` berisi:

- **Peluang**: keyword diurutkan menurut skor (volume 40%, konversi 35%, pesaing sedikit 25%),
  dengan label **Emas** (sepertiga teratas di ketiganya), **Potensial** (skor ≥ 60), atau **Lewati**.
- **Selera**: untuk setiap keyword yang sudah dicari, dibaca dari ±20 listing teratas di Insights:
  - **tema populer**: kata atau frasa yang sering muncul di judul, misalnya "christmas (7), vintage (6)";
  - **harga yang benar-benar dibayar pembeli** dan rentang harga listing teratas;
  - **kesulitan masuk**:
    - **Sulit** kalau pemain teratas rata-rata punya ribuan ulasan atau hampir semuanya Bestseller;
    - **Mudah** kalau ulasannya masih sedikit;
    - **Sedang** di antaranya;
  - **5 contoh listing teratas** (klik untuk melihat gambarnya).

  Kolom *Harga pasar* dan *Kesulitan masuk* juga muncul di sheet Peluang.
- **Semua data**: semua angka mentah, baik hasil cari maupun hasil panen.
- **Antrean**: keyword berikutnya yang akan dicari.

## 6. Mode kenal-halaman (kalau diminta)

```bash
bash kenali.command
```

Mode ini merekam data halaman saat Anda mencari keyword secara manual. Hanya tab Marketplace
Insights yang direkam. Nilai sensitif (token, cookie, email, dan sejenisnya) disensor otomatis,
tetapi **screenshot berisi apa pun yang tampil di layar**. Kirim file `rekaman/kenali-*.json`
ke Claude.

## 7. Pengaturan

`config.toml` berisi kuota, jeda, bobot skor, dan pengaturan lain. Angka yang melewati batas
keras (misalnya kuota di atas 30 per hari) otomatis dikoreksi.

## 8. Risiko yang perlu Anda ketahui

- **Ketentuan Etsy melarang akses otomatis.** Desain alat ini menekan risikonya: pelan, volume kecil,
  Chrome asli dari IP Anda sendiri, dan langsung berhenti saat ada tanda bahaya. Tetapi risikonya
  tidak bisa dihilangkan sepenuhnya, dan akun seller Anda yang menanggungnya.
- Etsy bisa mengubah halamannya kapan saja. Kalau itu terjadi, alat ini berhenti dengan aman.
