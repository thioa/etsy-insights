"""Meniru `python -m etsy_insights run` untuk tes SessionRunner."""
import signal
import sys
import time
from pathlib import Path

args = sys.argv[1:]
log = Path(args[args.index("--log-file") + 1])


def bye(*_):
    with log.open("a", encoding="utf-8") as f:
        f.write("12:00:03 Stopped: Stopped by you.\n")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal.SIG_IGN if "--ignore-term" in args else bye)
log.parent.mkdir(parents=True, exist_ok=True)
log.write_text("12:00:00 [1/3] alpha\n12:00:01   1000 searches, 5 related keywords (5 new)\n12:00:02 [2/3] beta\n",
               encoding="utf-8")
while True:
    time.sleep(0.05)
