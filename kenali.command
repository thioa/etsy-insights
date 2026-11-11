#!/bin/bash
# Mode kenal-halaman: rekam data Marketplace Insights saat Anda mencari keyword secara manual.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Belum terpasang. Klik dua kali setup.command dulu."
  read -r -p "Tekan Enter untuk menutup..."
  exit 1
fi
.venv/bin/python -m etsy_insights kenali
read -r -p "Tekan Enter untuk menutup..."
