"""Menjalankan, memantau, dan menghentikan proses sesi (`python -m etsy_insights run`) untuk web app."""
from __future__ import annotations

import fcntl
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PACKAGE_PARENT = Path(__file__).resolve().parent.parent
_PROGRESS_RE = re.compile(r"\[(\d+)/(\d+)\] (.+)$")


@dataclass(frozen=True)
class RunnerStatus:
    running: bool
    source: str | None  # "app" | "terminal" | None
    current_keyword: str | None
    done: int
    limit: int | None
    log_tail: tuple[str, ...]
    stopping: bool


class RunnerBusy(Exception):
    """Sudah ada sesi yang berjalan (dari aplikasi atau Terminal)."""


def is_locked(lock_path: Path) -> bool:
    """True bila proses lain memegang kunci sesi."""
    if not lock_path.exists():
        return False
    with open(lock_path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False


def parse_progress(lines: Sequence[str]) -> tuple[str | None, int, int | None]:
    """(keyword yang sedang dicari, nomor pencarian, batas) dari baris "[n/m] keyword" terakhir."""
    for line in reversed(lines):
        match = _PROGRESS_RE.search(line.strip())
        if match:
            return match.group(3).strip(), int(match.group(1)), int(match.group(2))
    return None, 0, None


def _tail(path: Path | None, count: int) -> list[str]:
    if path is None or not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-count:]


class SessionRunner:
    def __init__(self, home: Path, *, command: Sequence[str] | None = None, stop_timeout: float = 30.0,
                 popen=subprocess.Popen, clock=time.monotonic) -> None:
        self._home = Path(home)
        self._command = list(command) if command else [sys.executable, "-m", "etsy_insights", "run"]
        self._stop_timeout = stop_timeout
        self._popen = popen
        self._clock = clock
        self._process = None
        self._log: Path | None = None
        self._stop_deadline: float | None = None

    @property
    def _lock_path(self) -> Path:
        return self._home / "data" / "sesi.lock"

    def _own_running(self) -> bool:
        if self._process is None:
            return False
        if self._process.poll() is not None:
            return False
        if self._stop_deadline is not None and self._clock() > self._stop_deadline:
            try:
                self._process.kill()
                self._process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                pass
            return self._process.poll() is None
        return True

    def start(self, test_run: bool = False, ignore_cooldown: bool = False) -> Path:
        if self._own_running() or is_locked(self._lock_path):
            raise RunnerBusy("A session is already running.")
        logs = self._home / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"session-{datetime.now():%Y%m%d-%H%M%S}.log"
        args = list(self._command)
        if test_run:
            args.append("--uji")
        if ignore_cooldown:
            args += ["--abaikan-pendinginan", "--yes"]
        args += ["--log-file", str(log)]
        env = dict(os.environ)
        env["ETSY_INSIGHTS_HOME"] = str(self._home)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(PACKAGE_PARENT), env.get("PYTHONPATH", "")) if p)
        output = open(log.with_suffix(".out"), "w", encoding="utf-8")
        try:
            self._process = self._popen(args, env=env, cwd=str(self._home), stdout=output,
                                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        start_new_session=True)
        finally:
            output.close()
        self._log = log
        self._stop_deadline = None
        return log

    def stop(self) -> bool:
        if not self._own_running():
            return False
        try:
            self._process.send_signal(signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return False
        self._stop_deadline = self._clock() + self._stop_timeout
        return True

    def _latest_log(self) -> Path | None:
        logs = self._home / "logs"
        if not logs.exists():
            return None
        candidates = sorted(logs.glob("*.log"), key=lambda p: p.stat().st_mtime)
        return candidates[-1] if candidates else None

    def status(self, tail: int = 20) -> RunnerStatus:
        if self._own_running():
            running, source, log = True, "app", self._log
        elif is_locked(self._lock_path):
            running, source, log = True, "terminal", self._latest_log()
        else:
            running, source, log = False, None, self._log or self._latest_log()
        lines = _tail(log, max(tail, 200))
        keyword, done, limit = parse_progress(lines)
        return RunnerStatus(running=running, source=source, current_keyword=keyword if running else None,
                            done=done, limit=limit, log_tail=tuple(lines[-tail:]),
                            stopping=running and source == "app" and self._stop_deadline is not None)
