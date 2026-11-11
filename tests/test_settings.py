from pathlib import Path

from etsy_insights.config import Config, load_config
from etsy_insights.settings import render_config, save_settings, settings_form

VALID = {"kuota_harian": "12", "jeda_min": "25", "jeda_max": "70", "durasi_sesi_menit": "40",
         "bobot_volume": "2", "bobot_conversion": "1", "bobot_kompetisi": "1"}


def test_shipped_config_is_rendered_default():
    assert Path("config.toml").read_text(encoding="utf-8") == render_config(Config())


def test_save_valid_settings_roundtrip_and_keeps_other_keys(tmp_path):
    (tmp_path / "config.toml").write_text("port_debug = 9333\n", encoding="utf-8")
    cfg, errors = save_settings(tmp_path, VALID)
    assert errors == {} and cfg.kuota_harian == 12 and cfg.jeda_antar_keyword_detik == (25, 70)
    loaded, warnings = load_config(tmp_path / "config.toml")
    assert loaded == cfg and warnings == [] and loaded.port_debug == 9333 and loaded.bobot == (0.5, 0.25, 0.25)
    assert settings_form(loaded)["kuota_harian"] == "12"


def test_save_rejects_out_of_range_without_writing(tmp_path):
    bad = dict(VALID, kuota_harian="40", jeda_min="10", jeda_max="5", durasi_sesi_menit="x",
               bobot_volume="0", bobot_conversion="0", bobot_kompetisi="0")
    cfg, errors = save_settings(tmp_path, bad)
    assert cfg is None and not (tmp_path / "config.toml").exists()
    assert set(errors) == {"kuota_harian", "jeda_min", "jeda_max", "durasi_sesi_menit", "bobot_volume"}
    assert "1 to 30" in errors["kuota_harian"]
