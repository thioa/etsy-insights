#!/bin/bash
# Etsy Insights launcher: finds Python 3.11+ and Google Chrome, then hands over to bootstrap.py.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
SYSCTL="${ETSY_INSIGHTS_SYSCTL:-/usr/sbin/sysctl}"  # dapat diganti untuk tes
ARCH="${ETSY_INSIGHTS_ARCH:-/usr/bin/arch}"

# On Apple chips, Finder can start this script under Rosetta (Intel emulation). Python and Chrome started
# from here would inherit it and run slowly, so restart natively first.
if [ "$("$SYSCTL" -n sysctl.proc_translated 2>/dev/null)" = "1" ]; then
  exec "$ARCH" -arm64 /bin/bash "$0" "$@"
fi

ask() {  # ask "message" "Button" -> 0 when the button was clicked
  /usr/bin/osascript -e "display dialog \"$1\" with title \"Etsy Insights\" buttons {\"Cancel\", \"$2\"} default button \"$2\" with icon caution" >/dev/null 2>&1
}

usable() {  # usable PYTHON -> 0 when it exists and may be run
  local path
  path="$(command -v "$1" 2>/dev/null)" || return 1
  # Without Apple's developer tools, /usr/bin/python3 only shows an "install the tools?" popup.
  if [ "$path" = "/usr/bin/python3" ]; then
    /usr/bin/xcode-select -p >/dev/null 2>&1 || return 1
  fi
  return 0
}

# python.org first, then Homebrew, then anything else on PATH. ETSY_INSIGHTS_PYTHONS overrides (tests).
CANDIDATES="${ETSY_INSIGHTS_PYTHONS-$(echo /Library/Frameworks/Python.framework/Versions/3.1[1-9]/bin/python3) /opt/homebrew/bin/python3 /usr/local/bin/python3 python3}"
PY=""
for c in $CANDIDATES; do
  if usable "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"
    break
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
