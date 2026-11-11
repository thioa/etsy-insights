#!/bin/bash
# Mode kenal-halaman: rekam data Marketplace Insights saat Anda mencari keyword secara manual.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Not installed yet. Run setup.command first."
  read -r -p "Press Enter to close..."
  exit 1
fi
.venv/bin/python -m etsy_insights kenali
read -r -p "Press Enter to close..."
