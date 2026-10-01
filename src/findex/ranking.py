"""M2 — ранжування: протокол Scorer, TfIdf, BM25, SearchResult, топ-k."""
from __future__ import annotations

import heapq
import math
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from findex.indexer import Index
from findex.models import Posting


@dataclass(frozen=True, order=True)
class SearchResult:
    """Порядок задає лише `_key = (score, -doc_id)`: sorted(results) — за зростанням
    релевантності, sorted(results, reverse=True) — найкращі першими; за рівних
    балів раніший doc_id вважається кращим (детермінований результат)."""

    doc_id: int = field(compare=False)
    score: float = field(compare=False)
    title: str = field(compare=False, default="")
    snippet: str = field(compare=False, default="", repr=False)
    _key: tuple = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_key", (self.score, -self.doc_id))

    def __str__(self) -> str:
        return f"{self.score:7.3f}  [{self.doc_id}] {self.title}"


@runtime_checkable
class Scorer(Protocol):
    """Структурний інтерфейс: будь-який об'єкт із таким методом — Scorer."""

    def score(self, term: str, posting: Posting, index: Index) -> float: ...


@dataclass(frozen=True)
class TfIdf:
    """(1 + ln tf) · ln(N / df) — сублінійний TF, щоб 10 входжень ≠ 10× релевантності."""

    def score(self, term: str, posting: Posting, index: Index) -> float:
        df = index.df(term)
        if posting.tf <= 0 or df == 0:
            return 0.0
        return (1.0 + math.log(posting.tf)) * math.log(index.num_docs / df)

    __call__ = score


@dataclass(frozen=True)
class BM25:
    """Okapi BM25 з IDF у варіанті Lucene (завжди ≥ 0).

    idf · tf·(k1+1) / (tf + k1·(1 − b + b·dl/avgdl))
    k1 — насичення TF; b — сила нормалізації за довжиною (b=0: довжина ігнорується).
    """

    k1: float = 1.5
    b: float = 0.75

    def idf(self, term: str, index: Index) -> float:
        df, n = index.df(term), index.num_docs
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def score(self, term: str, posting: Posting, index: Index) -> float:
        if posting.tf <= 0:
            return 0.0
        dl = index.doc_length(posting.doc_id)
        avgdl = index.avg_doc_length or 1.0
        norm = self.k1 * (1.0 - self.b + self.b * dl / avgdl)
        return self.idf(term, index) * posting.tf * (self.k1 + 1.0) / (posting.tf + norm)

    __call__ = score


def score_docs(index: Index, terms: Iterable[str], candidates: Collection[int],
               scorer: Scorer) -> dict[int, float]:
    """Акумулятор: score[doc] += вага кожного терміна. Лише для документів-кандидатів
    (результат Boolean-обчислення дерева запиту)."""
    scores = dict.fromkeys(candidates, 0.0)
    for term in terms:
        for p in index.get(term, ()):
            if p.doc_id in scores:
                scores[p.doc_id] += scorer.score(term, p, index)
    return scores


def top_k(scores: dict[int, float], k: int) -> list[tuple[int, float]]:
    """O(n log k) замість sorted(...)[:k] — O(n log n). Ключ (score, -doc_id) = ті самі
    тай-брейки, що й у SearchResult."""
    return heapq.nlargest(k, scores.items(), key=lambda kv: (kv[1], -kv[0]))
