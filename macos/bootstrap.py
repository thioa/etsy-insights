"""Etsy Insights launcher (runs with the Mac's own Python; standard library only).

Prepares the app's Python environment once, offers to import data from an older etsy-insights
folder, starts the local web server in the background and opens it in the browser.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_NAME = "Etsy Insights"
APP_PORT_DEFAULT = 8765
SETUP_MESSAGE = "Setting up Etsy Insights (one time, 1–2 minutes)…"
IMPORT_ITEMS = ("data", "keywords.txt", "rekaman")  # never config.toml: its old defaults are unsafe now


class SetupError(Exception):
    pass


def app_home() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def resources_layout(res: Path) -> tuple[Path, Path]:
    """(requirements.txt, folder that contains the etsy_insights package)."""
    res = Path(res)
    if (res / "app").is_dir() and (res / "requirements.txt").exists():
        return res / "requirements.txt", res / "app"
    return res.parent / "requirements.txt", res.parent  # running from the source folder


def read_port(home: Path) -> int:
    config = Path(home) / "config.toml"
    if config.exists():
        match = re.search(r"^\s*port_web\s*=\s*(\d+)", config.read_text(encoding="utf-8", errors="replace"), re.M)
        if match:
            return int(match.group(1))
    return APP_PORT_DEFAULT


def requirements_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def venv_python(home: Path) -> Path:
    return Path(home) / "venv" / "bin" / "python"


def ensure_venv(home: Path, python: str, requirements: Path, *, run=subprocess.run, notify=None,
                force: bool = False) -> Path:
    """Create or update the app's venv when requirements.txt changed. Returns the venv's python."""
    home = Path(home)
    stamp = home / ".requirements-hash"
    digest = requirements_hash(requirements)
    target = venv_python(home)
    if not force and stamp.exists() and stamp.read_text(encoding="utf-8").strip() == digest:
        return target
    if notify:
        notify(SETUP_MESSAGE)
    log = home / "setup.log"
    with open(log, "w", encoding="utf-8") as out:
        steps = ([python, "-m", "venv", str(home / "venv")],
                 [str(target), "-m", "pip", "install", "--upgrade", "pip"],
                 [str(target), "-m", "pip", "install", "-r", str(requirements)])
        for args in steps:
            if run(args, stdout=out, stderr=subprocess.STDOUT).returncode != 0:
                raise SetupError(f"Etsy Insights could not finish its setup. Check your internet connection "
                                 f"and open it again. Details: {log}")
    stamp.write_text(digest, encoding="utf-8")
    return target


def needs_import(home: Path) -> bool:
    return not (Path(home) / "data" / "etsy.db").exists() and not (Path(home) / ".import-asked").exists()


def import_old_data(src: Path, home: Path) -> list[str]:
    copied = []
    for name in IMPORT_ITEMS:
        source, target = Path(src) / name, Path(home) / name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
            copied.append(name)
        elif source.is_file():
            shutil.copy2(source, target)
            copied.append(name)
    return copied


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ping(port: int) -> str:
    """"ours" if Etsy Insights answers on the port, "other" if something else does, "none" if nothing."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a system proxy
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/ping", timeout=1) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return "ours" if isinstance(data, dict) and data.get("app") == "etsy-insights" else "other"
    except urllib.error.HTTPError:
        return "other"
    except (urllib.error.URLError, OSError, ValueError):
        return "other" if _port_open(port) else "none"


def _env(home: Path, app_dir: Path) -> dict:
    env = dict(os.environ)
    env["ETSY_INSIGHTS_HOME"] = str(home)
    env["PYTHONPATH"] = str(app_dir)
    return env


def start_server(venv_py: Path, app_dir: Path, home: Path, port: int, *, popen=subprocess.Popen) -> None:
    log = open(Path(home) / "server.log", "a", encoding="utf-8")
    try:
        popen([str(venv_py), "-m", "etsy_insights", "web", "--port", str(port)], env=_env(home, app_dir),
              cwd=str(home), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
              start_new_session=True)
    finally:
        log.close()


def wait_for_server(port: int, timeout: float = 20, *, ping=ping, sleep=time.sleep) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if ping(port) == "ours":
            return True
        sleep(0.5)
    return False


def _osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True)


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


class MacDialogs:
    def notify(self, message: str) -> None:
        _osascript(f'display notification "{_quote(message)}" with title "{APP_NAME}"')

    def error(self, message: str) -> None:
        _osascript(f'display dialog "{_quote(message)}" with title "{APP_NAME}" buttons {{"OK"}} '
                   f'default button "OK" with icon caution')

    def ask_import(self) -> Path | None:
        answer = _osascript(
            f'display dialog "Import data from an older etsy-insights folder? (keywords, results, recordings)" '
            f'with title "{APP_NAME}" buttons {{"Skip", "Choose folder…"}} default button "Choose folder…"')
        if answer.returncode != 0 or "Choose folder" not in answer.stdout:
            return None
        chosen = _osascript('POSIX path of (choose folder with prompt "Choose your old etsy-insights folder")')
        path = chosen.stdout.strip()
        return Path(path) if chosen.returncode == 0 and path else None


def _open_in_browser(url: str) -> None:
    subprocess.run(["/usr/bin/open", url])


def main(argv: list[str], *, dialogs=None, open_url=None, ping=ping, popen=subprocess.Popen,
         run=subprocess.run, python: str = sys.executable) -> int:
    dialogs = dialogs or MacDialogs()
    open_url = open_url or _open_in_browser
    home = app_home()
    home.mkdir(parents=True, exist_ok=True)
    requirements, app_dir = resources_layout(Path(__file__).resolve().parent)

    def venv() -> Path:
        target = ensure_venv(home, python, requirements, run=run, notify=dialogs.notify)
        if not target.exists():
            target = ensure_venv(home, python, requirements, run=run, notify=dialogs.notify, force=True)
        return target

    if argv[:1] == ["--cli"]:  # Terminal fallback: etsy-insights --cli run --uji
        try:
            target = venv()
        except SetupError as exc:
            print(exc)
            return 1
        return run([str(target), "-m", "etsy_insights", *argv[1:]], env=_env(home, app_dir)).returncode

    port = read_port(home)
    url = f"http://127.0.0.1:{port}/"
    state = ping(port)
    if state == "ours":
        open_url(url)
        return 0
    if state == "other":
        dialogs.error(f"Port {port} is in use by another program. Change port_web in Settings, "
                      f"or quit the other program.")
        return 1
    try:
        target = venv()
    except SetupError as exc:
        dialogs.error(str(exc))
        return 1
    if needs_import(home):
        source = dialogs.ask_import()
        if source:
            import_old_data(Path(source), home)
        (home / ".import-asked").write_text("yes", encoding="utf-8")
    start_server(target, app_dir, home, port, popen=popen)
    if not wait_for_server(port, ping=ping):
        dialogs.error(f"Etsy Insights could not start. Details: {home / 'server.log'}")
        return 1
    open_url(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
