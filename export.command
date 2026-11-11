#!/bin/bash
# Buat file Excel berisi daftar peluang terbaru di folder hasil/.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Belum terpasang. Klik dua kali setup.command dulu."
  read -r -p "Tekan Enter untuk menutup..."
  exit 1
fi
.venv/bin/python -m etsy_insights export && open hasil
read -r -p "Tekan Enter untuk menutup..."
