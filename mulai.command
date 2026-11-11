#!/bin/bash
# Sesi harian: pencarian pelan di Chrome "Etsy Riset". Opsi: --uji (3 pencarian), --abaikan-pendinginan
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Belum terpasang. Jalankan setup.command dulu."
  read -r -p "Tekan Enter untuk menutup..."
  exit 1
fi
.venv/bin/python -m etsy_insights run "$@"
read -r -p "Tekan Enter untuk menutup..."
