"""Kelola daftar keyword pengguna (keywords.txt + database) dari web app."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .store import Store, _decode_text, normalize_keyword, read_keywords_file

FILE_NAME = "keywords.txt"


@dataclass(frozen=True)
class UserKeyword:
    keyword: str
    status: str


def _path(home: Path) -> Path:
    return Path(home) / FILE_NAME


def _read_text(path: Path) -> str:
    return _decode_text(path.read_bytes()) if path.exists() else ""


def add_keywords(home: Path, store: Store, text: str, now: datetime) -> list[str]:
    """Tambahkan keyword baru (satu per baris) ke keywords.txt; komentar dan isi lama tetap utuh."""
    path = _path(home)
    existing = set(read_keywords_file(path))
    new: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        keyword = normalize_keyword(line)
        if keyword and keyword not in existing and keyword not in new:
            new.append(keyword)
    if new:
        current = _read_text(path)
        if current and not current.endswith("\n"):
            current += "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current + "".join(f"{k}\n" for k in new), encoding="utf-8")
    store.sync_user_keywords(read_keywords_file(path), now)
    return new


def remove_keyword(home: Path, store: Store, keyword: str) -> bool:
    """Hapus keyword pengguna yang masih menunggu. Keyword yang sudah dicari tidak bisa dihapus."""
    wanted = normalize_keyword(keyword)
    item = store.get(wanted)
    if item is None or item.source != "user" or item.status != "pending":
        return False
    path = _path(home)
    lines = _read_text(path).splitlines(keepends=True)
    kept = [line for line in lines if line.strip().startswith("#") or normalize_keyword(line) != wanted]
    path.write_text("".join(kept), encoding="utf-8")
    store.remove_user_keyword(item.id)
    return True


def prioritize(home: Path, store: Store, keyword: str, now: datetime) -> bool:
    """Jadikan keyword hasil panen keyword pengguna, sehingga dicari pertama di sesi berikutnya."""
    wanted = normalize_keyword(keyword)
    if store.get(wanted) is None:
        return False
    add_keywords(home, store, wanted, now)
    item = store.get(wanted)
    return item is not None and item.source == "user" and item.status == "pending"


def list_user_keywords(home: Path, store: Store) -> list[UserKeyword]:
    result = []
    for keyword in read_keywords_file(_path(home)):
        item = store.get(keyword)
        result.append(UserKeyword(keyword, item.status if item is not None else "pending"))
    return result
