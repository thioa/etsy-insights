"""Membaca dan menyimpan pengaturan (config.toml) dari halaman Settings, tetap di dalam batas keamanan."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from .config import Config, load_config

FORM_FIELDS = ("kuota_harian", "jeda_min", "jeda_max", "durasi_sesi_menit",
               "bobot_volume", "bobot_conversion", "bobot_kompetisi")
FILE_NAME = "config.toml"
MAX_PAUSE = 600


def _num(value: float | int) -> str:
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() and abs(value) >= 1 else repr(value)
    return str(value)


def _pair(values: tuple) -> str:
    return f"[{_num(values[0])}, {_num(values[1])}]"


def render_config(cfg: Config) -> str:
    """Seluruh config.toml dengan komentar bahasa Inggris."""
    volume, conversion, competition = cfg.bobot
    return f"""# Etsy Insights settings. Delete a line to use the default value.
# Values outside the safety limits are corrected automatically (with a warning).

# Searches per day (Mac's date). Each search harvests about 130-180 related keywords. Safety limit: max 30.
kuota_harian = {cfg.kuota_harian}

# How long one session may run, including pauses and breaks (minutes). Safety limit: max 60.
durasi_sesi_menit = {cfg.durasi_sesi_menit}

# Random pause between searches in seconds [min, max]. Safety limit: min not below 15.
jeda_antar_keyword_detik = {_pair(cfg.jeda_antar_keyword_detik)}

# After this many searches [min, max], take a longer break.
istirahat_setiap = {_pair(cfg.istirahat_setiap)}

# Length of the longer break in seconds [min, max].
istirahat_detik = {_pair(cfg.istirahat_detik)}

# Pause between typed letters in milliseconds [min, max]. Safety limit: min not below 40.
kecepatan_ketik_ms = {_pair(cfg.kecepatan_ketik_ms)}

# How long to "read" the results in seconds [min, max]. Safety limit: min not below 3.
waktu_baca_detik = {_pair(cfg.waktu_baca_detik)}

# Maximum related keywords saved per search.
keyword_terkait_maks = {cfg.keyword_terkait_maks}

# How far to follow related keywords from your own keywords. Safety limit: max 3.
kedalaman_maks = {cfg.kedalaman_maks}

# A searched keyword is searched again after this many days. Safety limit: min 7.
cek_ulang_setelah_hari = {cfg.cek_ulang_setelah_hari}

# Pause after a captcha/verification/403/429, in hours. Safety limit: min 12.
pendinginan_jam = {cfg.pendinginan_jam}

# Keywords with fewer searches per month than this are not ranked.
volume_minimum = {cfg.volume_minimum}

# Port for the 'Etsy Riset' Chrome connection. Change only if another program uses it.
port_debug = {cfg.port_debug}

# Port for the Etsy Insights app in your browser (http://127.0.0.1:PORT).
port_web = {cfg.port_web}

# Score weights. They are normalized automatically so they add up to 1.
[bobot]
volume = {_num(volume)}
conversion = {_num(conversion)}
kompetisi = {_num(competition)}
"""


def settings_form(cfg: Config) -> dict[str, str]:
    volume, conversion, competition = cfg.bobot
    return {
        "kuota_harian": str(cfg.kuota_harian),
        "jeda_min": _num(cfg.jeda_antar_keyword_detik[0]),
        "jeda_max": _num(cfg.jeda_antar_keyword_detik[1]),
        "durasi_sesi_menit": str(cfg.durasi_sesi_menit),
        "bobot_volume": _num(volume),
        "bobot_conversion": _num(conversion),
        "bobot_kompetisi": _num(competition),
    }


def _whole(text: str | None) -> int | None:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _number(text: str | None) -> float | None:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def save_settings(home: Path, form: Mapping[str, str]) -> tuple[Config | None, dict[str, str]]:
    """Validasi formulir Settings, lalu tulis config.toml. Mengembalikan (config, {}) atau (None, errors)."""
    errors: dict[str, str] = {}
    quota = _whole(form.get("kuota_harian"))
    if quota is None or not 1 <= quota <= 30:
        errors["kuota_harian"] = "Enter a whole number from 1 to 30."
    pause_min = _whole(form.get("jeda_min"))
    if pause_min is None or not 15 <= pause_min <= MAX_PAUSE:
        errors["jeda_min"] = f"Enter seconds from 15 to {MAX_PAUSE}."
    pause_max = _whole(form.get("jeda_max"))
    lowest_max = pause_min if pause_min is not None and 15 <= pause_min <= MAX_PAUSE else 15
    if pause_max is None or not lowest_max <= pause_max <= MAX_PAUSE:
        errors["jeda_max"] = f"Must be at least the minimum pause and at most {MAX_PAUSE}."
    duration = _whole(form.get("durasi_sesi_menit"))
    if duration is None or not 1 <= duration <= 60:
        errors["durasi_sesi_menit"] = "Enter minutes from 1 to 60."
    weights = []
    for name in ("bobot_volume", "bobot_conversion", "bobot_kompetisi"):
        weight = _number(form.get(name))
        if weight is None or weight < 0:
            errors[name] = "Enter a number of 0 or more."
        weights.append(weight)
    if "bobot_volume" not in errors and all(w is not None and w >= 0 for w in weights) and sum(weights) <= 0:
        errors["bobot_volume"] = "At least one weight must be above 0."
    if errors:
        return None, errors

    path = Path(home) / FILE_NAME
    current, _ = load_config(path)
    total = sum(weights)
    updated = replace(current, kuota_harian=quota, jeda_antar_keyword_detik=(pause_min, pause_max),
                      durasi_sesi_menit=duration, bobot=tuple(w / total for w in weights))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(updated), encoding="utf-8")
    saved, _ = load_config(path)
    return saved, {}
