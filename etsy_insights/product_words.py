"""Kata produk POD: kamus bawaan, normalisasi, dan pencocokan keyword ↔ jenis produk (spec Tahap 4 §7)."""
from __future__ import annotations

import re
from collections.abc import Sequence

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
_CONSONANT_Y = re.compile(r"([^aeiou\W\d_])y$")


def _base_form(word: str) -> str:
    if word.endswith("ies"):
        word = word[:-1]  # babies → babie, hoodies → hoodie
    elif word.endswith(("ses", "xes", "ches", "shes")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        word = word[:-1]
    return _CONSONANT_Y.sub(r"\1ie", word)  # baby → babie, hoody → hoodie


def normalize_words(text: str) -> tuple[str, ...]:
    cleaned = _NOT_WORD.sub(" ", _SEPARATORS.sub(" ", text.lower()))
    return tuple(_base_form(word) for word in cleaned.split())


def _contains(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    size = len(phrase)
    return size > 0 and any(tuple(tokens[i:i + size]) == tuple(phrase) for i in range(len(tokens) - size + 1))


def matches_tokens(tokens: Sequence[str], words: Sequence[str]) -> bool:
    """Seperti `matches`, untuk keyword yang sudah dinormalkan (dipakai saat mencocokkan ribuan keyword)."""
    return any(_contains(tokens, normalize_words(phrase)) for phrase in words)


def matches(keyword: str, words: Sequence[str]) -> bool:
    return matches_tokens(normalize_words(keyword), words)


def words_for_title(title: str) -> list[str]:
    tokens = normalize_words(title)
    words: list[str] = []
    for main, synonyms in DICTIONARY:
        entry = (main, *synonyms)
        if any(_contains(tokens, normalize_words(phrase)) for phrase in entry):
            words.extend(word for word in entry if word not in words)
    return words
