#!/bin/bash
# Etsy Insights launcher: finds Python 3.11+ and Google Chrome, then hands over to bootstrap.py.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"

ask() {  # ask "message" "Button" -> 0 when the button was clicked
  /usr/bin/osascript -e "display dialog \"$1\" with title \"Etsy Insights\" buttons {\"Cancel\", \"$2\"} default button \"$2\" with icon caution" >/dev/null 2>&1
}

PY=""
for c in /Library/Frameworks/Python.framework/Versions/3.1[1-9]/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"
  fi
done

if [ -z "$PY" ]; then
  if ask "Etsy Insights needs Python 3.11 or newer. Install it from python.org, then open Etsy Insights again." "Download Python"; then
    /usr/bin/open "https://www.python.org/downloads/macos/"
  fi
  exit 1
fi

if [ ! -d "/Applications/Google Chrome.app" ]; then
  if ask "Etsy Insights needs Google Chrome in the Applications folder." "Download Chrome"; then
    /usr/bin/open "https://www.google.com/chrome/"
  fi
  exit 1
fi

exec "$PY" -I "$RES/bootstrap.py" "$@"
