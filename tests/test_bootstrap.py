import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).parent.parent / "macos" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class Dialogs:
    def __init__(self, choose=None):
        self.msgs, self.choose = [], choose
        self.answers = list(choose) if isinstance(choose, list) else None

    def notify(self, m):
        self.msgs.append(("notify", m))

    def error(self, m):
        self.msgs.append(("error", m))

    def info(self, m):
        self.msgs.append(("info", m))

    def ask_import(self):
        if self.answers is not None:
            return self.answers.pop(0) if self.answers else None
        return self.choose


OK = type("R", (), {"returncode": 0})()


def test_ensure_venv_runs_once_per_requirements(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("flask\n")
    calls = []

    def run(args, **kw):
        calls.append(args)
        return OK
    bootstrap.ensure_venv(tmp_path, "python3", req, run=run)
    n = len(calls)
    bootstrap.ensure_venv(tmp_path, "python3", req, run=run)
    assert n >= 2 and len(calls) == n
    req.write_text("flask\nopenpyxl\n")
    bootstrap.ensure_venv(tmp_path, "python3", req, run=run)
    assert len(calls) > n


def test_import_old_data_skips_config(tmp_path):
    old = tmp_path / "old"
    (old / "data").mkdir(parents=True)
    (old / "rekaman").mkdir()
    (old / "data" / "etsy.db").write_bytes(b"db")
    (old / "keywords.txt").write_text("mug\n")
    (old / "config.toml").write_text("kuota_harian = 50\n")
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(bootstrap.import_old_data(old, home)) == ["data", "keywords.txt", "rekaman"]
    assert (home / "data" / "etsy.db").read_bytes() == b"db" and not (home / "config.toml").exists()


def test_read_port(tmp_path):
    assert bootstrap.read_port(tmp_path) == 8765
    (tmp_path / "config.toml").write_text("port_web = 9001\n")
    assert bootstrap.read_port(tmp_path) == 9001


def test_resources_layout(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "requirements.txt").write_text("x")
    assert bootstrap.resources_layout(tmp_path) == (tmp_path / "requirements.txt", tmp_path / "app")
    repo_res = Path(__file__).parent.parent / "macos"
    req, app_dir = bootstrap.resources_layout(repo_res)
    assert req == repo_res.parent / "requirements.txt" and (app_dir / "etsy_insights").is_dir()


def test_main_reuses_running_server(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "app_home", lambda: tmp_path)
    opened = []
    assert bootstrap.main([], dialogs=Dialogs(), open_url=opened.append, ping=lambda p: "ours") == 0
    assert opened == ["http://127.0.0.1:8765/"]


def test_main_reports_foreign_port(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "app_home", lambda: tmp_path)
    d = Dialogs()
    assert bootstrap.main([], dialogs=d, open_url=lambda u: None, ping=lambda p: "other") == 1
    assert d.msgs[0][0] == "error" and "8765" in d.msgs[0][1]


def test_main_first_launch_imports_and_starts(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(bootstrap, "app_home", lambda: home)
    old = tmp_path / "old"
    (old / "data").mkdir(parents=True)
    (old / "data" / "etsy.db").write_bytes(b"db")
    states = iter(["none", "none", "ours"])
    started, opened = [], []
    rc = bootstrap.main([], dialogs=Dialogs(choose=old), open_url=opened.append, ping=lambda p: next(states),
                        popen=lambda args, **kw: started.append((args, kw)), run=lambda args, **kw: OK)
    assert rc == 0 and (home / "data" / "etsy.db").exists() and (home / ".import-asked").exists()
    args, kw = started[0]
    assert args[1:] == ["-m", "etsy_insights", "web", "--port", "8765"]
    assert kw["env"]["ETSY_INSIGHTS_HOME"] == str(home)
    assert opened == ["http://127.0.0.1:8765/"]


def _old_folder(tmp_path):
    old = tmp_path / "old"
    (old / "data").mkdir(parents=True)
    (old / "data" / "etsy.db").write_bytes(b"db")
    return old


def _first_launch(tmp_path, monkeypatch, dialogs):
    home = tmp_path / "home"
    monkeypatch.setattr(bootstrap, "app_home", lambda: home)
    states = iter(["none", "ours"])
    rc = bootstrap.main([], dialogs=dialogs, open_url=lambda u: None, ping=lambda p: next(states),
                        popen=lambda args, **kw: None, run=lambda args, **kw: OK)
    return rc, home


def test_import_asks_again_after_a_folder_without_data(tmp_path, monkeypatch):
    old = _old_folder(tmp_path)
    wrong = tmp_path / "Downloads"
    wrong.mkdir()
    d = Dialogs(choose=[wrong, old])
    rc, home = _first_launch(tmp_path, monkeypatch, d)
    assert rc == 0 and (home / "data" / "etsy.db").exists()
    kinds = [kind for kind, _ in d.msgs if kind != "notify"]
    assert kinds == ["error", "info"]
    assert str(wrong) in d.msgs[[k for k, _ in d.msgs].index("error")][1]
    info = d.msgs[[k for k, _ in d.msgs].index("info")][1]
    assert "mulai.command" in info and str(old) in info


def test_import_can_be_skipped_after_a_wrong_folder(tmp_path, monkeypatch):
    wrong = tmp_path / "empty"
    wrong.mkdir()
    rc, home = _first_launch(tmp_path, monkeypatch, Dialogs(choose=[wrong, None]))
    assert rc == 0 and not (home / "data").exists() and (home / ".import-asked").exists()


def test_import_failure_is_shown_and_asked_again(tmp_path, monkeypatch):
    old = _old_folder(tmp_path)
    real = bootstrap.import_old_data
    calls = []

    def flaky(src, home):
        calls.append(src)
        if len(calls) == 1:
            raise PermissionError("Operation not permitted")
        return real(src, home)
    monkeypatch.setattr(bootstrap, "import_old_data", flaky)
    d = Dialogs(choose=[old, old])
    rc, home = _first_launch(tmp_path, monkeypatch, d)
    assert rc == 0 and len(calls) == 2 and (home / "data" / "etsy.db").exists()
    assert any(kind == "error" and "Operation not permitted" in m for kind, m in d.msgs)


def test_launch_shows_unexpected_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "app_home", lambda: tmp_path)

    def broken_ping(port):
        raise OverflowError("port must be 0-65535.")
    d = Dialogs()
    assert bootstrap.launch([], dialogs=d, open_url=lambda u: None, ping=broken_ping) == 1
    assert d.msgs[-1][0] == "error" and "OverflowError" in d.msgs[-1][1]
    assert "OverflowError" in (tmp_path / "launcher-error.log").read_text()


def _fake_python(path, calls):
    path.write_text(f'#!/bin/sh\necho "$0" >> "{calls}"\nexit 0\n')
    path.chmod(0o755)
    return path


def _run_launcher(tmp_path, candidates):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "ETSY_INSIGHTS_PYTHONS": " ".join(map(str, candidates))}
    launcher = Path(__file__).parent.parent / "macos" / "launcher.sh"
    return subprocess.run(["/bin/bash", str(launcher)], env=env, capture_output=True, text=True, timeout=20)


def test_launcher_uses_the_first_suitable_python(tmp_path):
    calls = tmp_path / "calls.txt"
    first, second = _fake_python(tmp_path / "py1", calls), _fake_python(tmp_path / "py2", calls)
    _run_launcher(tmp_path, [tmp_path / "missing", first, second])
    assert calls.read_text().split() == [str(first)]


@pytest.mark.skipif(not os.path.exists("/usr/bin/python3") or os.path.exists("/usr/bin/xcode-select"),
                    reason="needs /usr/bin/python3 without Apple's developer tools")
def test_launcher_skips_the_system_python_stub_without_developer_tools(tmp_path):
    calls = tmp_path / "calls.txt"
    fallback = _fake_python(tmp_path / "py1", calls)
    _run_launcher(tmp_path, ["/usr/bin/python3", fallback])
    assert calls.read_text().split() == [str(fallback)]
