from pathlib import Path

import pytest

from etsy_insights.config import Config, ConfigError, load_config


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "tidak-ada.toml") == (Config(), [])


def test_shipped_config_equals_defaults():
    cfg, warnings = load_config(Path("config.toml"))
    assert cfg == Config() and warnings == []


def test_defaults_match_spec():
    c = Config()
    assert (c.kuota_harian, c.durasi_sesi_menit) == (15, 45)
    assert c.jeda_antar_keyword_detik == (20, 60) and c.istirahat_setiap == (8, 12)
    assert c.istirahat_detik == (120, 300) and c.kecepatan_ketik_ms == (60, 180)
    assert c.waktu_baca_detik == (5, 15) and c.keyword_terkait_maks == 200
    assert (c.kedalaman_maks, c.cek_ulang_setelah_hari, c.pendinginan_jam) == (2, 30, 24)
    assert c.volume_minimum == 100 and c.bobot == (0.40, 0.35, 0.25) and c.port_debug == 9222


def test_hard_caps_clamp_with_warning(tmp_path):
    cfg, warnings = load_config(write(tmp_path,
        "kuota_harian = 500\ndurasi_sesi_menit = 120\njeda_antar_keyword_detik = [5, 10]\n"
        "kecepatan_ketik_ms = [10, 50]\nwaktu_baca_detik = [1, 2]\nkedalaman_maks = 9\n"
        "cek_ulang_setelah_hari = 1\npendinginan_jam = 2\n"))
    assert (cfg.kuota_harian, cfg.durasi_sesi_menit) == (30, 60)
    assert cfg.jeda_antar_keyword_detik == (15, 15)
    assert cfg.kecepatan_ketik_ms == (40, 50) and cfg.waktu_baca_detik == (3, 3)
    assert (cfg.kedalaman_maks, cfg.cek_ulang_setelah_hari, cfg.pendinginan_jam) == (3, 7, 12)
    assert len(warnings) == 8


def test_reversed_range_is_sorted(tmp_path):
    cfg, warnings = load_config(write(tmp_path, "jeda_antar_keyword_detik = [60, 20]\n"))
    assert cfg.jeda_antar_keyword_detik == (20, 60)


def test_weights_normalized(tmp_path):
    cfg, _ = load_config(write(tmp_path, "[bobot]\nvolume = 2\nconversion = 1\nkompetisi = 1\n"))
    assert cfg.bobot == (0.5, 0.25, 0.25)


def test_all_zero_weights_fall_back_to_default(tmp_path):
    cfg, warnings = load_config(write(tmp_path, "[bobot]\nvolume = 0\nconversion = 0\nkompetisi = 0\n"))
    assert cfg.bobot == (0.40, 0.35, 0.25) and any("bobot" in w for w in warnings)


def test_invalid_toml_raises_config_error_with_line(tmp_path):
    with pytest.raises(ConfigError, match=r"config\.toml.*line 1"):
        load_config(write(tmp_path, "kuota_harian = = 5\n"))


def test_wrong_type_uses_default_with_warning(tmp_path):
    cfg, warnings = load_config(write(tmp_path, 'kuota_harian = "lima puluh"\ndurasi_sesi_menit = -5\n'))
    assert (cfg.kuota_harian, cfg.durasi_sesi_menit) == (15, 45)
    assert any("kuota_harian" in w for w in warnings) and any("durasi_sesi_menit" in w for w in warnings)


def test_unknown_key_warns(tmp_path):
    cfg, warnings = load_config(write(tmp_path, "kuota = 10\n"))
    assert cfg == Config() and any("kuota" in w for w in warnings)


def test_config_with_bom_is_fine(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes("﻿kuota_harian = 30\n".encode("utf-8"))
    assert load_config(p)[0].kuota_harian == 30


def test_config_not_utf8_raises_config_error(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes("# catatan café\nkuota_harian = 30\n".encode("cp1252"))
    with pytest.raises(ConfigError, match="UTF-8"):
        load_config(p)


def test_non_finite_numbers_use_default(tmp_path):
    cfg, warnings = load_config(write(tmp_path,
        "kuota_harian = inf\nistirahat_setiap = [8, inf]\njeda_antar_keyword_detik = [20, nan]\n"))
    assert (cfg.kuota_harian, cfg.istirahat_setiap, cfg.jeda_antar_keyword_detik) == (15, (8, 12), (20, 60))
    assert len(warnings) == 3


def test_etsy_quota_exhausted():
    from etsy_insights.models import EtsyQuota
    assert not EtsyQuota(15, 15, 5, False, True).exhausted
    assert EtsyQuota(15, 5, 5, False, True).exhausted
    assert EtsyQuota(15, 15, 5, True, True).exhausted and EtsyQuota(15, 15, 5, False, False).exhausted
    assert not EtsyQuota(None, None, None, False, True).exhausted
