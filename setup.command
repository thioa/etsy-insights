#!/bin/bash
# Pemasangan sekali: membuat lingkungan Python dan memasang library yang dibutuhkan.
cd "$(dirname "$0")" || exit 1

tutup() { read -r -p "Press Enter to close..."; exit "$1"; }

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is not installed on this Mac."
  echo "Download it from https://www.python.org/downloads/macos/ , install it, then run setup.command again."
  tutup 1
fi

echo "Using $("$PY" --version)"
echo "Creating the Python environment (.venv) and installing libraries... (1-2 minutes)"
if ! "$PY" -m venv .venv || ! .venv/bin/pip install -q -r requirements.txt; then
  echo "Installation failed. Check your internet connection, then run setup.command again."
  tutup 1
fi

if [ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  echo "Warning: Google Chrome was not found in the Applications folder."
  echo "Install it from https://www.google.com/chrome/ before running kenali.command."
fi

mkdir -p data hasil logs rekaman
echo ""
echo "Done. Next step: run mulai.command --uji (test run)."
tutup 0
