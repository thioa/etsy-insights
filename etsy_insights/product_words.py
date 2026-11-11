"""Kata produk POD: kamus bawaan, normalisasi, dan pencocokan keyword ↔ jenis produk (spec Tahap 4 §7)."""
from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

# (kata utama, sinonim) — urutan sama dengan tabel spec §7.
DICTIONARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sweatshirt", ("crewneck", "crew neck", "jumper")),
    ("hoodie", ("hooded sweatshirt", "hoody")),
    ("t shirt", ("tee", "tshirt", "shirt")),
    ("tank top", ("tank",)),
    ("mug", ("coffee mug", "cup")),
    ("tumbler", ("travel mug",)),
    ("water bottle", ("bottle",)),
    ("tote bag", ("tote",)),
    ("poster", ("wall art", "art print", "print")),
    ("canvas", ("canvas print",)),
    ("blanket", ("throw blanket",)),
    ("pillow", ("throw pillow", "cushion")),
    ("phone case", ("iphone case",)),
    ("sticker", ("decal",)),
    ("ornament", ("christmas ornament",)),
    ("hat", ("cap", "baseball cap", "trucker hat", "beanie")),
    ("baby bodysuit", ("onesie", "baby onesie")),
    ("socks", ("sock",)),
    ("notebook", ("journal",)),
    ("puzzle", ("jigsaw puzzle",)),
    ("mouse pad", ("mousepad",)),
    ("apron", ()),
    ("backpack", ()),
)

_SEPARATORS = re.compile(r"[-_/&]")
_NOT_WORD = re.compile(r"[^\w\s]|_")


# Kata tunggal yang berakhiran -s (bukan bentuk jamak): canvas, canvases → canvas.
KEEP_S = frozenset({"canvas", "atlas", "bus", "lens", "iris"})


def _base_form(word: str) -> str:
    if word.endswith("ies"):
        word = word[:-1]  # babies → babie, hoodies → hoodie
    elif word.endswith(("sses", "xes", "ches", "shes")):
        word = word[:-2]  # glasses → glass, boxes → box
    elif word.endswith("ses") and word[:-2] in KEEP_S:
        word = word[:-2]  # canvases → canvas
    elif word in KEEP_S:
        pass
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        word = word[:-1]  # cases → case, mugs → mug, tees → tee
    if len(word) > 1 and word[-1] == "y" and word[-2].isalpha() and word[-2] not in "aeiou":
        word = word[:-1] + "ie"  # baby → babie, hoody → hoodie
    return word


@lru_cache(maxsize=65536)
def normalize_words(text: str) -> tuple[str, ...]:
    cleaned = _NOT_WORD.sub(" ", _SEPARATORS.sub(" ", text.lower()))
    return tuple(_base_form(word) for word in cleaned.split())


def _contains(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    size = len(phrase)
    if size == 0 or phrase[0] not in tokens:
        return False
    return any(tuple(tokens[i:i + size]) == tuple(phrase) for i in range(len(tokens) - size + 1))


def matches_tokens(tokens: Sequence[str], words: Sequence[str]) -> bool:
    """Seperti `matches`, untuk keyword yang sudah dinormalkan (dipakai saat mencocokkan ribuan keyword)."""
    return any(_contains(tokens, normalize_words(phrase)) for phrase in words)


def matches(keyword: str, words: Sequence[str]) -> bool:
    return matches_tokens(normalize_words(keyword), words)


def _last_match(tokens: Sequence[str], phrase: Sequence[str]) -> tuple[int, int] | None:
    """(posisi akhir kecocokan terakhir, panjang frasa), atau None."""
    size = len(phrase)
    ends = [i + size for i in range(len(tokens) - size + 1) if size and tuple(tokens[i:i + size]) == tuple(phrase)]
    return (max(ends), size) if ends else None


def words_for_title(title: str) -> list[str]:
    """Kata produk untuk judul blueprint: entri kamus untuk kata benda utamanya.

    Kata benda utama = kecocokan yang berakhir paling belakang di judul; kalau sama, frasa terpanjang.
    "Hooded Sweatshirt" → hoodie (bukan sweatshirt), "Cotton Canvas Tote Bag" → tote bag (bukan canvas).
    """
    tokens = normalize_words(title)
    best: tuple[tuple[int, int], tuple[str, ...]] | None = None
    for main, synonyms in DICTIONARY:
        entry = (main, *synonyms)
        hits = [m for m in (_last_match(tokens, normalize_words(phrase)) for phrase in entry) if m]
        if hits and (best is None or max(hits) > best[0]):
            best = (max(hits), entry)
    return list(dict.fromkeys(best[1])) if best else []
