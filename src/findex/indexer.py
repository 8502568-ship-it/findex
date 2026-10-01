"""M1 — `Index`: інвертований індекс як об'єкт, що поводиться «по-пайтонівськи».

    with open_index("index.pkl") as ix:
        len(ix), "python" in ix, ix["python"], list(ix)[:5], ix

`Index` — це `collections.abc.Mapping[str, list[Posting]]`: достатньо реалізувати
`__getitem__`, `__len__`, `__iter__` — решту (`keys`, `items`, `get`, ...) дає ABC.
Обгортає будь-який бекенд Лаби 2 (ObjectIndex / ArrayIndex / MmapIndex).
"""
from __future__ import annotations

import functools
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from findex.models import Posting
from findex.store import load


class Index(Mapping):
    def __init__(self, backend) -> None:
        self._b = backend
        # у всіх трьох бекендів є dict term -> щось: postings або _toc
        self._terms = backend.postings if hasattr(backend, "postings") else backend._toc

    # ------------------------- протокол Mapping -------------------------
    def __len__(self) -> int:
        return len(self._terms)

    def __contains__(self, term: object) -> bool:
        # Mapping.__contains__ викликав би __getitem__ і будував би список постінгів
        return term in self._terms

    def __getitem__(self, term: str) -> list[Posting]:
        if term not in self._terms:
            raise KeyError(term)
        raw = self._b.postings[term] if hasattr(self._b, "postings") else None
        if isinstance(raw, list):  # ObjectIndex: вже список Posting
            return raw
        return [Posting(d, tf) for d, tf in zip(self._b.doc_ids(term), self._b.tfs(term))]

    def __iter__(self) -> Iterator[str]:
        return iter(self._terms)

    def __repr__(self) -> str:
        return f"Index(terms={len(self):_}, docs={self.num_docs:_})"

    # Mapping визначає __eq__ як порівняння всіх пар — для 500k термінів це дуже
    # дорого, а для lru_cache ключем має бути хешований об'єкт. Тож індекс — це
    # сутність з ідентичністю: рівний лише собі.
    def __eq__(self, other: object) -> bool:
        return self is other

    __hash__ = object.__hash__

    # ----------------------- обчислювані атрибути -----------------------
    @property
    def num_docs(self) -> int:
        return len(self._b.doc_meta)

    @functools.cached_property
    def avg_doc_length(self) -> float:
        """Рахується один раз на індекс (а не для кожного документа в BM25)."""
        lengths = self._b.doc_lengths
        return sum(lengths.values()) / len(lengths) if lengths else 0.0

    @functools.cached_property
    def has_positions(self) -> bool:
        return any(p.positions for t in self._terms for p in self[t][:1])

    def doc_length(self, doc_id: int) -> int:
        return self._b.doc_lengths[doc_id]

    def df(self, term: str) -> int:
        return self._b.df(term)

    def title(self, doc_id: int) -> str:
        return self._b.doc_meta[doc_id].title

    def path(self, doc_id: int) -> str:
        return self._b.doc_meta[doc_id].path

    def all_doc_ids(self) -> set[int]:
        return set(self._b.doc_meta)

    @property
    def backend(self):
        return self._b

    def close(self) -> None:
        close = getattr(self._b, "close", None)
        if close:
            close()


@contextmanager
def open_index(path) -> Iterator[Index]:
    """Все до `yield` — це __enter__, усе після — __exit__; finally виконується
    і при return, і при винятку в тілі `with`."""
    ix = Index(load(path))
    try:
        yield ix
    finally:
        ix.close()
