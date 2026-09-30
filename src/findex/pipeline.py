"""Адаптер до пайплайну Лаби 1 (src/findex/corpus.py та tokenize.py).

Якщо модулі Лаби 1 знайдено — беремо їх; інакше працює автономний запасний
варіант (щоб код можна було запускати й перевіряти окремо).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple


class RawDoc(NamedTuple):
    path: str
    title: str
    text: str


_TITLE = re.compile(r"^Title:\s*(.+?)\s*$", re.MULTILINE)


def _title(text: str, path) -> str:
    """Назва книги з заголовка Project Gutenberg, інакше ім'я файлу."""
    m = _TITLE.search(text[:5000])
    return m.group(1) if m else Path(str(path)).stem


try:  # ---- пайплайн Лаби 1 ----
    from findex.corpus import iter_documents
    from findex.tokenize import tokenize

    def iter_docs(root) -> Iterator[RawDoc]:
        for d in iter_documents(root):
            yield RawDoc(str(d.path), _title(d.text, d.path), d.text)

except ImportError:  # ---- запасний варіант ----
    _WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)

    def tokenize(text: str) -> Iterator[str]:
        for m in _WORD.finditer(text.casefold()):
            yield m.group(0)

    def iter_docs(root) -> Iterator[RawDoc]:
        for p in sorted(Path(root).rglob("*.txt")):
            text = p.read_text(encoding="utf-8", errors="replace")
            yield RawDoc(str(p), _title(text, p), text)
