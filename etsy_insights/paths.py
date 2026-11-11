"""Lokasi data aplikasi. Web app memakai ~/Library/Application Support/Etsy Insights lewat ETSY_INSIGHTS_HOME."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_HOME = "ETSY_INSIGHTS_HOME"


def app_home() -> Path:
    value = os.environ.get(ENV_HOME)
    return Path(value) if value else PROJECT_ROOT


def excel_dir(home: Path) -> Path:
    """Saat berjalan sebagai aplikasi, Excel disimpan di Documents agar mudah ditemukan."""
    if os.environ.get(ENV_HOME):
        return Path.home() / "Documents" / "Etsy Insights"
    return Path(home) / "hasil"
