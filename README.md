# Etsy Insights: Pencari Peluang Keyword (Tahap 1)

Alat ini membantu mencari keyword Etsy dengan **volume pencarian besar**,
**conversion rate tinggi**, dan **pesaing sedikit**. Datanya diambil dari halaman
Marketplace Insights di Shop Manager Anda sendiri. Semua data tersimpan di Mac Anda.

> **Status: Tahap 1.** Paket ini berisi pemasangan, mode kenal-halaman (`kenali.command`),
> dan pembuatan Excel (`export.command`). Tombol sesi harian (`mulai.command`) dibuat
> di Tahap 2, setelah rekaman `kenali` Anda dianalisis.

## 1. Pemasangan (sekali saja)

1. **Unzip** `etsy-insights-tahap1.zip`, lalu pindahkan folder `etsy-insights` ke tempat
   yang mudah ditemukan, misalnya `Documents`.
2. **Izinkan file `.command` dibuka.** macOS memblokir file dari internet pada pembukaan
   pertama. Pilih salah satu:
   - Klik kanan `setup.command` → **Open** → **Open**, atau
   - Buka Terminal lalu jalankan (sesuaikan lokasi foldernya):
     ```bash
     xattr -dr com.apple.quarantine ~/Documents/etsy-insights
     ```
3. **Klik dua kali `setup.command`.** Script ini memeriksa Python 3.11+ (kalau belum
   ada, Anda diarahkan ke python.org), lalu memasang library yang dibutuhkan.
   Google Chrome harus sudah terpasang di folder Applications.

## 2. Mode kenal-halaman (`kenali.command`)

Tujuannya agar pembaca data di Tahap 2 ditulis dari data asli halaman Anda, bukan
tebakan. **Di mode ini tidak ada otomatisasi:** Anda sendiri yang mencari.

1. Klik dua kali `kenali.command`.
2. Chrome terbuka dengan profil terpisah bernama **"Etsy Riset"**. Profil Chrome
   Anda sehari-hari tidak disentuh.
3. **Pertama kali:** login ke Etsy di jendela Chrome itu (mungkin Etsy meminta
   verifikasi email karena "perangkat baru"), lalu tekan Enter di Terminal.
4. Di Marketplace Insights, ketik satu keyword dan tunggu sampai hasilnya tampil.
5. Kembali ke Terminal dan **tekan Enter** untuk merekam.
6. Ulangi langkah 4–5 untuk **2–3 keyword**, lalu ketik `selesai` dan Enter.
7. Rekaman tersimpan di `rekaman/kenali-YYYYMMDD-HHMM.json`. **Kirim file itu ke Claude**,
   bersama screenshot halaman Insights untuk satu keyword.

Hanya tab Marketplace Insights yang direkam. Sebelum disimpan, nilai yang dikenali
sebagai sensitif diganti `[DIHAPUS]`: token, nonce, cookie, sesi, kata sandi, alamat email,
dan nilai di bawah kunci seperti `email`, `phone`, atau `address`. Header request dan
cookie tidak direkam sama sekali. Penyensoran ini otomatis dan berbasis pola, jadi tidak
dijamin sempurna. **Screenshot berisi apa pun yang tampil di layar**, jadi tutup dulu
informasi pribadi (misalnya data pembeli) sebelum merekam.

## 3. Excel (`export.command`)

Klik dua kali `export.command`. File `hasil/peluang-YYYY-MM-DD.xlsx` dibuat, lalu folder
`hasil` terbuka. Di Tahap 1 isinya masih kosong, karena data baru terkumpul setelah
sesi harian berjalan di Tahap 2.

## 4. Pengaturan

- `keywords.txt`: daftar keyword Anda, satu per baris.
- `config.toml`: kuota harian, jeda, bobot skor, dan lain-lain. Nilai default-nya sudah
  aman. Angka yang melewati batas keras (misalnya kuota di atas 100 per hari)
  otomatis dikoreksi.

## 5. Risiko yang perlu Anda ketahui

- **Ketentuan Etsy melarang akses otomatis.** Desain alat ini menekan risiko: berjalan
  pelan, volume kecil, memakai browser Chrome asli dari IP Anda sendiri, dan langsung
  berhenti saat muncul CAPTCHA, verifikasi, atau error. Tetapi risikonya tidak bisa
  dihilangkan sepenuhnya, dan akun seller Anda yang menanggungnya.
- Etsy bisa mengubah halamannya kapan saja. Kalau itu terjadi, alat ini berhenti dengan
  aman dan meminta Anda menjalankan `kenali.command` lagi.

## 6. Langkah berikutnya (Tahap 2)

Setelah rekaman `kenali` diterima, Tahap 2 menambahkan:

- pembaca data Marketplace Insights,
- `mulai.command` untuk sesi harian (default 50 keyword, jeda 20–60 detik, maksimal 45 menit),
- mode uji coba 3 keyword.
