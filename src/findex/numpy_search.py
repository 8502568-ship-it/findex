from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Literal

import numpy as np

from findex.models import SearchResult
from findex.tokenize import tokenize

ScorerName = Literal["bm25", "tfidf"]


class NumpyIndex:
    """NumPy representation of postings and document lengths.

    Every posting list is stored as two int32 arrays: document ids and term
    frequencies. Document lengths are stored in one int32 array indexed by
    document id.
    """

    def __init__(
        self,
        postings: dict[str, tuple[np.ndarray, np.ndarray]],
        doc_lengths: np.ndarray,
        titles: dict[int, str],
        total_docs: int,
    ) -> None:
        self.postings = postings
        self.doc_lengths = doc_lengths
        self.titles = titles
        self.total_docs = total_docs

    @classmethod
    def from_index(cls, index) -> "NumpyIndex":
        postings = {}
        for term, plist in index.postings.items():
            postings[term] = (
                np.asarray([p.doc_id for p in plist], dtype=np.int32),
                np.asarray([p.term_frequency for p in plist], dtype=np.int32),
            )
        lengths = np.zeros(index.total_docs, dtype=np.int32)
        for doc_id, length in index.doc_lengths.items():
            if doc_id >= len(lengths):
                lengths = np.pad(lengths, (0, doc_id + 1 - len(lengths)))
            lengths[doc_id] = length
        return cls(postings, lengths, dict(index.doc_titles), index.total_docs)

    def search(
        self,
        query: str,
        k: int = 10,
        scorer: ScorerName = "bm25",
    ) -> list[SearchResult]:
        terms = list(tokenize(query))
        if not terms or self.total_docs == 0:
            return []

        avg_len = float(self.doc_lengths.mean()) if self.total_docs else 0.0
        doc_ids_parts: list[np.ndarray] = []
        score_parts: list[np.ndarray] = []

        for term in terms:
            pair = self.postings.get(term)
            if pair is None:
                continue
            doc_ids, tf = pair
            df = len(doc_ids)
            if scorer == "bm25":
                idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
                dl = self.doc_lengths[doc_ids].astype(np.float64)
                tf64 = tf.astype(np.float64)
                norm = 1.0 - 0.75 + 0.75 * (dl / avg_len if avg_len else 1.0)
                values = idf * (tf64 * 2.5) / (tf64 + 1.5 * norm)
            else:
                values = (1.0 + np.log(tf.astype(np.float64))) * math.log(
                    self.total_docs / df
                )
            doc_ids_parts.append(doc_ids)
            score_parts.append(values)

        if not doc_ids_parts:
            return []

        ids = np.concatenate(doc_ids_parts)
        vals = np.concatenate(score_parts)
        unique_ids, inverse = np.unique(ids, return_inverse=True)
        scores = np.zeros(len(unique_ids), dtype=np.float64)
        np.add.at(scores, inverse, vals)

        take = min(k, len(scores))
        if take < len(scores):
            candidates = np.argpartition(scores, -take)[-take:]
        else:
            candidates = np.arange(len(scores))
        ordered = sorted(
            candidates,
            key=lambda i: (-float(scores[i]), int(unique_ids[i])),
        )
        return [
            SearchResult(
                doc_id=int(unique_ids[i]),
                score=float(scores[i]),
                title=self.titles.get(int(unique_ids[i]), f"Doc {int(unique_ids[i])}"),
                snippet="",
            )
            for i in ordered
        ]


def benchmarkable_terms(index, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if term in index.postings]
