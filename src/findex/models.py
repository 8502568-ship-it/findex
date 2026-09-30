"""Структури даних індексу та три способи зберігання постінгів."""
from __future__ import annotations

from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Posting:
    doc_id: int
    tf: int
    positions: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DocMeta:
    doc_id: int
    path: str
    title: str


# Для M4: «звичайний» dataclass (з __dict__ на кожен екземпляр).
@dataclass
class PlainPosting:
    doc_id: int
    tf: int
    positions: tuple[int, ...] = ()


class Index(Protocol):
    doc_lengths: dict[int, int]
    doc_meta: dict[int, DocMeta]

    def terms(self) -> Sequence[str]: ...
    def df(self, term: str) -> int: ...
    def doc_ids(self, term: str) -> Sequence[int]: ...
    def tfs(self, term: str) -> Sequence[int]: ...


class _Base:
    def __init__(self) -> None:
        self.doc_lengths: dict[int, int] = {}
        self.doc_meta: dict[int, DocMeta] = {}

    @property
    def n_docs(self) -> int:
        return len(self.doc_meta)

    def all_doc_ids(self) -> list[int]:
        return sorted(self.doc_meta)


class ObjectIndex(_Base):
    """term -> list[Posting] (Posting або PlainPosting), відсортовано за doc_id."""

    kind = "object"

    def __init__(self, postings: dict | None = None) -> None:
        super().__init__()
        self.postings: dict[str, list] = postings if postings is not None else {}

    def terms(self):
        return list(self.postings)

    def df(self, term):
        return len(self.postings.get(term, ()))

    def doc_ids(self, term):
        return [p.doc_id for p in self.postings.get(term, ())]

    def tfs(self, term):
        return [p.tf for p in self.postings.get(term, ())]


class ArrayIndex(_Base):
    """term -> (array('I') doc_ids, array('I') tfs): жодних Python-об'єктів на постінг."""

    kind = "array"

    def __init__(self, postings: dict[str, tuple[array, array]] | None = None) -> None:
        super().__init__()
        self.postings = postings if postings is not None else {}

    def terms(self):
        return list(self.postings)

    def df(self, term):
        e = self.postings.get(term)
        return len(e[0]) if e else 0

    def doc_ids(self, term):
        e = self.postings.get(term)
        return e[0] if e else array("I")

    def tfs(self, term):
        e = self.postings.get(term)
        return e[1] if e else array("I")


class MmapIndex(_Base):
    """Бінарний формат через mmap: постінги читаються лише для запитаних термінів."""

    kind = "mmap"

    def __init__(self, view: memoryview, toc: dict[str, tuple[int, int]], mm, fh) -> None:
        super().__init__()
        self._view = view
        self._toc = toc  # term -> (offset_in_blob_bytes, count)
        self._mm = mm
        self._fh = fh

    def terms(self):
        return list(self._toc)

    def df(self, term):
        e = self._toc.get(term)
        return e[1] if e else 0

    def _slice(self, term, second: bool):
        e = self._toc.get(term)
        if not e:
            return array("I")
        off, n = e
        start = off + (4 * n if second else 0)
        return self._view[start : start + 4 * n].cast("I")

    def doc_ids(self, term):
        return self._slice(term, False)

    def tfs(self, term):
        return self._slice(term, True)

    def close(self):
        self._view.release()
        self._mm.close()
        self._fh.close()
