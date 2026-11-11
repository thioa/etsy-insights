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


def test_selling_fields_saved_and_validated(tmp_path):
    form = settings_form(Config()) | {"fee_etsy_persen": "6.5", "fee_etsy_tetap_usd": "0.25", "margin_minimum_usd": "4"}
    cfg, errors = save_settings(tmp_path, form)
    assert errors == {} and (cfg.fee_etsy_persen, cfg.fee_etsy_tetap_usd, cfg.margin_minimum_usd) == (6.5, 0.25, 4.0)
    bad = form | {"fee_etsy_persen": "31", "fee_etsy_tetap_usd": "x", "margin_minimum_usd": "101"}
    cfg, errors = save_settings(tmp_path, bad)
    assert cfg is None and errors == {"fee_etsy_persen": "Enter a percentage from 0 to 30.",
                                      "fee_etsy_tetap_usd": "Enter an amount from 0 to 5.",
                                      "margin_minimum_usd": "Enter an amount from 0 to 100."}


def test_advisor_limit_saved_and_validated(tmp_path):
    cfg, errors = save_settings(tmp_path, settings_form(Config()) | {"advisor_batas_bulanan_usd": "25"})
    assert errors == {} and cfg.advisor_batas_bulanan_usd == 25.0
    assert "advisor_batas_bulanan_usd = 25" in (tmp_path / "config.toml").read_text(encoding="utf-8")
    cfg, errors = save_settings(tmp_path, settings_form(Config()) | {"advisor_batas_bulanan_usd": "abc"})
    assert cfg is None and errors == {"advisor_batas_bulanan_usd": "Enter an amount from 0 to 1000."}
    cfg, errors = save_settings(tmp_path, VALID)  # formulir lama tanpa field ini: nilai sekarang tetap
    assert errors == {} and cfg.advisor_batas_bulanan_usd == 25.0


def test_settings_page_has_advisor_section(tmp_path):
    from tests.web_helpers import FakeRunner, TOKEN, client, seeded_home
    from etsy_insights.web import create_app
    app = create_app(seeded_home(tmp_path / "home"), token=TOKEN, runner=FakeRunner())
    html = client(app).get("/settings").get_data(as_text=True)
    assert "<legend>Advisor</legend>" in html and "Advisor monthly limit (USD)" in html
    assert "0 means no limit. Each run costs about US$0.40–0.80." in html
    assert 'name="advisor_batas_bulanan_usd"' in html
