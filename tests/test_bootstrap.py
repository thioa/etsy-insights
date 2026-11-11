import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).parent.parent / "macos" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class Dialogs:
    def __init__(self, choose=None):
        self.msgs, self.choose = [], choose

    def notify(self, m):
        self.msgs.append(("notify", m))

    def error(self, m):
        self.msgs.append(("error", m))

    def ask_import(self):
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
