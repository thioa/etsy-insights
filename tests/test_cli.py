import fcntl
import os
import signal
import subprocess
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest

from openpyxl import load_workbook

import etsy_insights.__main__ as cli
from etsy_insights.__main__ import main
from tests.helpers import T0, FakeClock, FakePage, fake_parse


def project(tmp_path, keywords="boho wall art\nmacrame\n", config=""):
    (tmp_path / "keywords.txt").write_text(keywords, encoding="utf-8")
    (tmp_path / "config.toml").write_text(config, encoding="utf-8")
    return tmp_path


def test_cli_status(tmp_path, capsys):
    assert main(["status"], base_dir=project(tmp_path), now=lambda: T0) == 0
    out = capsys.readouterr().out
    assert "Queue: 2 queued" in out and "Today: 0/15 searches" in out


def test_cli_export(tmp_path, capsys):
    assert main(["export"], base_dir=project(tmp_path), now=lambda: T0) == 0
    path = tmp_path / "hasil" / "peluang-2026-11-11.xlsx"
    assert path.exists() and load_workbook(path)["Queue"].max_row == 4


def test_cli_bad_config_returns_1(tmp_path, capsys):
    assert main(["status"], base_dir=project(tmp_path, config="kuota_harian = = 1\n"), now=lambda: T0) == 1
    out = capsys.readouterr().out
    assert "line 1" in out and "Traceback" not in out


def test_command_scripts_are_valid_and_executable():
    for name in ("setup.command", "kenali.command", "export.command", "mulai.command"):
        p = Path(name)
        assert p.stat().st_mode & 0o111, name
        assert subprocess.run(["bash", "-n", name]).returncode == 0


def test_cli_playwright_error_has_no_traceback(tmp_path, capsys, monkeypatch):
    from playwright.sync_api import Error as PlaywrightError
    import etsy_insights.__main__ as cli

    def boom(*a, **k):
        raise PlaywrightError("Target page has been closed")
    monkeypatch.setattr(cli, "_kenali", boom)
    assert main(["kenali"], base_dir=project(tmp_path), now=lambda: T0) == 1
    out = capsys.readouterr().out
    assert "Chrome" in out and "Traceback" not in out


def test_cli_unexpected_error_has_no_traceback(tmp_path, capsys, monkeypatch):
    import etsy_insights.__main__ as cli

    def boom(*a, **k):
        raise RuntimeError("aneh")
    monkeypatch.setattr(cli, "_status", boom)
    assert main(["status"], base_dir=project(tmp_path), now=lambda: T0) == 1
    out = capsys.readouterr().out
    assert "Unexpected error" in out and "aneh" in out


def patch_page(monkeypatch, page):
    @contextmanager
    def fake_open(cfg, pacer, rng, log):
        yield page
    monkeypatch.setattr(cli, "_open_insights", fake_open)
    monkeypatch.setattr(cli, "parse_search", fake_parse)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)


def test_cli_run_uji(tmp_path, capsys, monkeypatch):
    page = FakePage(FakeClock(T0))
    patch_page(monkeypatch, page)
    assert main(["run", "--uji"], base_dir=project(tmp_path, keywords="a\nb\nc\nd\n"), now=lambda: T0) == 0
    out = capsys.readouterr().out
    assert "Keywords checked: 3" in out and page.searched == ["a", "b", "c"]
    assert len(list((tmp_path / "logs").glob("sesi-*.log"))) == 1


def test_cli_run_refuses_when_locked(tmp_path, capsys, monkeypatch):
    page = FakePage(FakeClock(T0))
    patch_page(monkeypatch, page)
    base = project(tmp_path)
    (base / "data").mkdir()
    with open(base / "data" / "sesi.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["run"], base_dir=base, now=lambda: T0) == 1
    assert "Another session is running" in capsys.readouterr().out and page.opened == 0


def test_lock_released_after_error(tmp_path, monkeypatch):
    page = FakePage(FakeClock(T0))
    patch_page(monkeypatch, page)

    def boom(keyword):
        raise RuntimeError("aneh")
    page.search = boom
    base = project(tmp_path)
    assert main(["run"], base_dir=base, now=lambda: T0) == 1
    with cli.session_lock(base / "data" / "sesi.lock") as ok:
        assert ok


def test_cli_ignore_cooldown_requires_yes(tmp_path, capsys, monkeypatch):
    from etsy_insights.store import Store
    base = project(tmp_path)
    s = Store(base / "data" / "etsy.db")
    sid = s.start_session(T0)
    s.end_session(sid, T0, "tanda_bahaya", T0 + timedelta(hours=24))
    s.close()
    page = FakePage(FakeClock(T0))
    patch_page(monkeypatch, page)
    assert main(["run", "--abaikan-pendinginan"], base_dir=base, now=lambda: T0, input_fn=lambda p: "no") == 1
    assert page.opened == 0
    assert main(["run", "--abaikan-pendinginan"], base_dir=base, now=lambda: T0, input_fn=lambda p: "YES") == 0
    assert page.opened == 1


def test_sigterm_becomes_keyboard_interrupt():
    with pytest.raises(KeyboardInterrupt):
        with cli.interrupt_on_signals():
            os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


def test_cli_export_includes_selera(tmp_path, capsys):
    from etsy_insights.store import Store
    from tests.helpers import make_metrics
    from tests.test_parser import load_raw
    base = project(tmp_path, keywords="sweatshirt\n")
    s = Store(base / "data" / "etsy.db")
    s.sync_user_keywords(["sweatshirt"], T0)
    s.save_result(s.get("sweatshirt").id, make_metrics(volume=46395, level=0, comp=1863632),
                  load_raw("sweatshirt"), T0, "t")
    s.close()
    assert main(["export"], base_dir=base, now=lambda: T0) == 0
    sel = load_workbook(tmp_path / "hasil" / "peluang-2026-11-11.xlsx")["Buyer taste"]
    assert sel.cell(3, 1).value == "sweatshirt"


def test_cli_status_error_reason_is_readable(tmp_path, capsys):
    from etsy_insights.store import Store
    base = project(tmp_path)
    s = Store(base / "data" / "etsy.db")
    sid = s.start_session(T0)
    s.end_session(sid, T0, "error", None)
    s.close()
    assert main(["status"], base_dir=base, now=lambda: T0) == 0
    assert "unexpected error" in capsys.readouterr().out
