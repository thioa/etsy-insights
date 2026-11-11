"""Membaca config.toml dan memaksakan batas keras keamanan."""
from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """config.toml tidak bisa dibaca."""


@dataclass(frozen=True)
class Config:
    kuota_harian: int = 15  # pencarian per hari
    durasi_sesi_menit: int = 45
    jeda_antar_keyword_detik: tuple[float, float] = (20, 60)
    istirahat_setiap: tuple[int, int] = (8, 12)
    istirahat_detik: tuple[float, float] = (120, 300)
    kecepatan_ketik_ms: tuple[float, float] = (60, 180)
    waktu_baca_detik: tuple[float, float] = (5, 15)
    keyword_terkait_maks: int = 200  # keyword panen per pencarian
    kedalaman_maks: int = 2
    cek_ulang_setelah_hari: int = 30
    pendinginan_jam: int = 24
    volume_minimum: int = 100
    bobot: tuple[float, float, float] = (0.40, 0.35, 0.25)  # volume, conversion, kompetisi
    port_debug: int = 9222
    port_web: int = 8765
    fee_etsy_persen: float = 9.5  # % dari harga jual
    fee_etsy_tetap_usd: float = 0.45  # per penjualan
    margin_minimum_usd: float = 5.0  # batas Ready to sell


# Batas keras: (minimum, maksimum). Untuk rentang, minimum berlaku pada batas bawah.
HARD_LIMITS: dict[str, tuple[float | None, float | None]] = {
    "kuota_harian": (None, 30),
    "durasi_sesi_menit": (None, 60),
    "jeda_antar_keyword_detik": (15, None),
    "kecepatan_ketik_ms": (40, None),
    "waktu_baca_detik": (3, None),
    "kedalaman_maks": (None, 3),
    "cek_ulang_setelah_hari": (7, None),
    "pendinginan_jam": (12, None),
}

_INT_KEYS = {"kuota_harian", "durasi_sesi_menit", "keyword_terkait_maks", "kedalaman_maks",
             "cek_ulang_setelah_hari", "pendinginan_jam", "volume_minimum", "port_debug", "port_web"}
# Nilai di luar rentang ini tidak dibatasi, tetapi diganti default (port yang salah tidak bisa "dibulatkan").
_RANGE_OR_DEFAULT = {"port_web": (1024, 65535), "fee_etsy_persen": (0, 30), "fee_etsy_tetap_usd": (0, 5),
                     "margin_minimum_usd": (0, 100)}
_FLOAT_KEYS = {"fee_etsy_persen", "fee_etsy_tetap_usd", "margin_minimum_usd"}
_RANGE_KEYS = {"jeda_antar_keyword_detik", "istirahat_setiap", "istirahat_detik",
               "kecepatan_ketik_ms", "waktu_baca_detik"}
_INT_RANGE_KEYS = {"istirahat_setiap"}
_WEIGHT_KEYS = ("volume", "conversion", "kompetisi")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _parse_scalar(key: str, value: Any, default: int, warnings: list[str]) -> int:
    if not _is_number(value) or value < 0 or (key in _INT_KEYS and value != int(value)):
        kind = "a whole number" if key in _INT_KEYS else "a number"
        warnings.append(f"{key}: value '{value}' is not valid (must be {kind} of 0 or more), using default {default}.")
        return default
    if key in _RANGE_OR_DEFAULT:
        low, high = _RANGE_OR_DEFAULT[key]
        if not low <= value <= high:
            warnings.append(f"{key}: {value} must be from {low} to {high}, using default {default}.")
            return default
    if key in _FLOAT_KEYS:
        return float(value)
    lo, hi = HARD_LIMITS.get(key, (None, None))
    result = int(value)
    if hi is not None and result > hi:
        warnings.append(f"{key}: {result} is above the safety limit, using {int(hi)}.")
        result = int(hi)
    if lo is not None and result < lo:
        warnings.append(f"{key}: {result} is below the safety limit, using {int(lo)}.")
        result = int(lo)
    return result


def _parse_range(key: str, value: Any, default: tuple, warnings: list[str]) -> tuple:
    if (not isinstance(value, list) or len(value) != 2
            or not all(_is_number(v) and v >= 0 for v in value)):
        warnings.append(f"{key}: must be [min, max] with numbers of 0 or more, using default {list(default)}.")
        return default
    lo, hi = sorted(value)
    if key in _INT_RANGE_KEYS:
        lo, hi = int(lo), int(hi)
    hard_lo, _ = HARD_LIMITS.get(key, (None, None))
    if hard_lo is not None and lo < hard_lo:
        warnings.append(f"{key}: minimum {lo} is below the safety limit, using {hard_lo}.")
        lo = hard_lo
    hi = max(hi, lo)
    return (lo, hi)


def _parse_weights(value: Any, default: tuple, warnings: list[str]) -> tuple:
    if not isinstance(value, dict):
        warnings.append("bobot: must be a [bobot] table, using defaults.")
        return default
    for unknown in set(value) - set(_WEIGHT_KEYS):
        warnings.append(f"bobot.{unknown}: unknown key, ignored.")
    raw = []
    for name, dflt in zip(_WEIGHT_KEYS, default):
        w = value.get(name, dflt)
        if not _is_number(w) or w < 0:
            warnings.append(f"bobot.{name}: value '{w}' is not valid, using default {dflt}.")
            w = dflt
        raw.append(float(w))
    total = sum(raw)
    if total <= 0:
        warnings.append("bobot: all weights are zero, using defaults 0.40/0.35/0.25.")
        return default
    return tuple(w / total for w in raw)


def load_config(path: Path) -> tuple[Config, list[str]]:
    """Baca config.toml. Mengembalikan (config, daftar peringatan)."""
    path = Path(path)
    if not path.exists():
        return Config(), []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError("config.toml is not UTF-8 text. Open it in TextEdit and save it as plain text "
                          "(UTF-8).") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        match = re.search(r"line (\d+)", str(exc))
        line = match.group(1) if match else "?"
        raise ConfigError(f"config.toml is not valid at line {line}: {exc}") from exc

    defaults = Config()
    known = {f.name for f in fields(Config)}
    warnings: list[str] = []
    changes: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            warnings.append(f"{key}: unknown key, ignored.")
            continue
        default = getattr(defaults, key)
        if key == "bobot":
            changes[key] = _parse_weights(value, default, warnings)
        elif key in _RANGE_KEYS:
            changes[key] = _parse_range(key, value, default, warnings)
        else:
            changes[key] = _parse_scalar(key, value, default, warnings)
    return replace(defaults, **changes), warnings
