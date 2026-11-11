Etsy Insights — cara memasang
=============================

1. Pasang Python (sekali saja), kalau belum ada:
   https://www.python.org/downloads/macos/  (pilih "macOS 64-bit universal2 installer")

2. Seret "Etsy Insights.app" ke folder Applications.

3. Pembukaan pertama: macOS menolak dengan pesan "Etsy Insights" Not Opened.
   Klik Done (JANGAN Move to Trash), lalu:
   System Settings -> Privacy & Security -> scroll ke bagian Security
   -> klik "Open Anyway" -> masukkan password -> "Open Anyway" lagi.
   Atau satu perintah di Terminal:
     xattr -dr com.apple.quarantine "/Applications/Etsy Insights.app"
   Cukup sekali.

4. Pembukaan pertama juga akan:
   - menyiapkan aplikasi (sekali, 1-2 menit; muncul notifikasi),
   - menawarkan impor data lama: pilih folder etsy-insights lama Anda
     (misalnya Downloads/etsy-insights, yang berisi folder "data"), atau klik Skip.

   Setelah impor, jangan jalankan mulai.command di folder lama lagi. Folder lama
   punya batas harian dan cooldown sendiri, jadi memakai keduanya bisa membuat
   Etsy curiga. Folder lama boleh dihapus.

5. Browser terbuka ke Etsy Insights. Mulai dari "Test run (3 searches)".

Printify (opsional): menu Printify -> tempel token (izin shops.read, products.read,
catalog.read) -> Sync now. Aplikasi hanya membaca dari Printify.

Keluar: Settings -> Quit Etsy Insights (lakukan ini juga sebelum mengganti aplikasi).
Data aplikasi: ~/Library/Application Support/Etsy Insights
File Excel: Documents/Etsy Insights
