#!/bin/bash
# Pemasangan sekali: membuat lingkungan Python dan memasang library yang dibutuhkan.
cd "$(dirname "$0")" || exit 1

tutup() { read -r -p "Tekan Enter untuk menutup..."; exit "$1"; }

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.11 atau lebih baru belum terpasang di Mac ini."
  echo "Unduh dari https://www.python.org/downloads/macos/ , pasang, lalu jalankan setup.command lagi."
  tutup 1
fi

echo "Memakai $("$PY" --version)"
echo "Membuat lingkungan Python (.venv) dan memasang library... (1-2 menit)"
if ! "$PY" -m venv .venv || ! .venv/bin/pip install -q -r requirements.txt; then
  echo "Pemasangan gagal. Periksa koneksi internet, lalu jalankan setup.command lagi."
  tutup 1
fi

if [ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  echo "Peringatan: Google Chrome tidak ditemukan di folder Applications."
  echo "Pasang dari https://www.google.com/chrome/ sebelum menjalankan kenali.command."
fi

mkdir -p data hasil logs rekaman
echo ""
echo "Selesai. Langkah berikutnya: klik dua kali kenali.command."
tutup 0
