import subprocess
from pathlib import Path

from openpyxl import load_workbook

from etsy_insights.__main__ import main
from tests.helpers import T0


def project(tmp_path, keywords="boho wall art\nmacrame\n", config=""):
    (tmp_path / "keywords.txt").write_text(keywords, encoding="utf-8")
    (tmp_path / "config.toml").write_text(config, encoding="utf-8")
    return tmp_path


def test_cli_status(tmp_path, capsys):
    assert main(["status"], base_dir=project(tmp_path), now=lambda: T0) == 0
    out = capsys.readouterr().out
    assert "Antrean: 2 menunggu" in out and "Hari ini: 0/50 keyword dicek" in out


def test_cli_export(tmp_path, capsys):
    assert main(["export"], base_dir=project(tmp_path), now=lambda: T0) == 0
    path = tmp_path / "hasil" / "peluang-2026-11-11.xlsx"
    assert path.exists() and load_workbook(path)["Antrean"].max_row == 4


def test_cli_bad_config_returns_1(tmp_path, capsys):
    assert main(["status"], base_dir=project(tmp_path, config="kuota_harian = = 1\n"), now=lambda: T0) == 1
    out = capsys.readouterr().out
    assert "baris 1" in out and "Traceback" not in out


def test_command_scripts_are_valid_and_executable():
    for name in ("setup.command", "kenali.command", "export.command"):
        p = Path(name)
        assert p.stat().st_mode & 0o111, name
        assert subprocess.run(["bash", "-n", name]).returncode == 0
