"""API key Anthropic: disimpan di file `anthropic-key` (izin 0600) di folder data aplikasi, tidak pernah ditampilkan."""
from __future__ import annotations

from pathlib import Path

from .secret_file import delete_secret, load_secret, save_secret

KEY_FILE = "anthropic-key"
BAD_KEY = "That does not look like an Anthropic API key."


def clean_key(text: str) -> str:
    """Buang semua spasi dan baris baru (key yang terpotong saat ditempel)."""
    return "".join(text.split())


def looks_like_key(key: str) -> bool:
    return key.startswith("sk-ant-") and len(key) >= 20 and all(33 <= ord(ch) <= 126 for ch in key)


def save_key(home: Path, key: str) -> str:
    cleaned = clean_key(key)
    if not looks_like_key(cleaned):
        raise ValueError(BAD_KEY)
    save_secret(home, KEY_FILE, cleaned)
    return cleaned


def load_key(home: Path) -> str | None:
    text = load_secret(home, KEY_FILE)
    key = clean_key(text) if text is not None else ""
    return key or None


def delete_key(home: Path) -> None:
    delete_secret(home, KEY_FILE)


def key_hint(key: str) -> str:
    return "…" + key[-4:]
