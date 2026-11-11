"""Token Printify: disimpan di file `printify-token` (izin 0600) di folder data aplikasi, tidak pernah ditampilkan."""
from __future__ import annotations

import re
from pathlib import Path

from .secret_file import delete_secret, load_secret, save_secret

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
    save_secret(home, TOKEN_FILE, cleaned)
    return cleaned


def load_token(home: Path) -> str | None:
    text = load_secret(home, TOKEN_FILE)
    token = clean_token(text) if text is not None else ""
    return token or None


def delete_token(home: Path) -> None:
    delete_secret(home, TOKEN_FILE)


def token_hint(token: str) -> str:
    return "…" + token[-4:]
