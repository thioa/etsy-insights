#!/bin/bash
# Sesi harian: pencarian pelan di Chrome "Etsy Riset". Opsi: --uji (3 pencarian), --abaikan-pendinginan
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Not installed yet. Run setup.command first."
  read -r -p "Press Enter to close..."
  exit 1
fi
.venv/bin/python -m etsy_insights run "$@"
read -r -p "Press Enter to close..."
