"""Rahasia kecil (token, API key) di folder data aplikasi: file berizin 0600, ditulis atomik."""
from __future__ import annotations

import os
from pathlib import Path


def save_secret(home: Path, name: str, value: str) -> None:
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    temp = home / f".{name}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(temp, 0o600)
    os.replace(temp, home / name)


def load_secret(home: Path, name: str) -> str | None:
    path = Path(home) / name
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def delete_secret(home: Path, name: str) -> None:
    (Path(home) / name).unlink(missing_ok=True)
