"""Token Printify: disimpan di file `printify-token` (izin 0600) di folder data aplikasi, tidak pernah ditampilkan."""
from __future__ import annotations

import os
import re
from pathlib import Path

TOKEN_FILE = "printify-token"
_BEARER = re.compile(r"^bearer(\s+|$)", re.IGNORECASE)


def clean_token(token: str) -> str:
    """Buang awalan "Bearer " dan semua spasi/baris baru (token yang terpotong saat ditempel)."""
    return "".join(_BEARER.sub("", token.strip()).split())


def looks_like_token(token: str) -> bool:
    """Token Printify hanya berisi karakter ASCII yang terlihat."""
    return bool(token) and all(33 <= ord(ch) <= 126 for ch in token)


def save_token(home: Path, token: str) -> str:
    cleaned = clean_token(token)
    if not looks_like_token(cleaned):
        raise ValueError("That does not look like a Printify token.")
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    temp = home / f".{TOKEN_FILE}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, cleaned.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(temp, 0o600)
    os.replace(temp, home / TOKEN_FILE)
    return cleaned


def load_token(home: Path) -> str | None:
    path = Path(home) / TOKEN_FILE
    if not path.exists():
        return None
    token = clean_token(path.read_text(encoding="utf-8"))
    return token or None


def delete_token(home: Path) -> None:
    (Path(home) / TOKEN_FILE).unlink(missing_ok=True)


def token_hint(token: str) -> str:
    return "…" + token[-4:]
