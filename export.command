#!/bin/bash
# Buat file Excel berisi daftar peluang terbaru di folder hasil/.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Not installed yet. Run setup.command first."
  read -r -p "Press Enter to close..."
  exit 1
fi
.venv/bin/python -m etsy_insights export && open hasil
read -r -p "Press Enter to close..."
