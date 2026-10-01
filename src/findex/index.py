import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from findex.models import DocId, Posting, SearchResult
from findex.scoring import BM25Scorer, Scorer, TFIDFScorer
from findex.tokenize import tokenize

log = logging.getLogger(__name__)


def merge_and(a: list[DocId], b: list[DocId]) -> list[DocId]:
    """Linear merge intersection for two sorted doc ID lists."""
    i, j = 0, 0
    res: list[DocId] = []
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            res.append(a[i])
            i += 1
            j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return res


def merge_or(a: list[DocId], b: list[DocId]) -> list[DocId]:
    """Linear merge union for two sorted doc ID lists."""
    i, j = 0, 0
    res: list[DocId] = []
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            res.append(a[i])
            i += 1
            j += 1
        elif a[i] < b[j]:
            res.append(a[i])
            i += 1
        else:
            res.append(b[j])
            j += 1
    while i < len(a):
        res.append(a[i])
        i += 1
    while j < len(b):
        res.append(b[j])
        j += 1
    return res


class InvertedIndex:
    def __init__(self) -> None:
        self.postings: dict[str, list[Posting]] = defaultdict(list)
        self.doc_lengths: dict[DocId, int] = {}
        self.doc_titles: dict[DocId, str] = {}
        self.total_docs: int = 0

    @property
    def avg_doc_len(self) -> float:
        if self.total_docs == 0:
            return 0.0
        return sum(self.doc_lengths.values()) / self.total_docs

    def add_document(self, doc_id: DocId, title: str, text: str, store_positions: bool = False) -> None:
        log.debug("Indexing doc_id=%d title=%s", doc_id, title)
        tokens = list(tokenize(text))
        self.doc_lengths[doc_id] = len(tokens)
        self.doc_titles[doc_id] = title
        self.total_docs += 1

        term_positions: dict[str, list[int]] = defaultdict(list)
        for pos, term in enumerate(tokens):
            term_positions[term].append(pos)

        for term, positions in term_positions.items():
            pos_list = positions if store_positions else []
            self.postings[term].append(
                Posting(doc_id=doc_id, term_frequency=len(positions), positions=pos_list)
            )

    def search(
        self,
        query: str,
        k: int = 10,
        scorer_name: Literal["bm25", "tfidf"] = "bm25",
    ) -> list[SearchResult]:
        tokens = list(tokenize(query))
        if not tokens:
            return []

        scorer: Scorer = BM25Scorer() if scorer_name == "bm25" else TFIDFScorer()
        scores: dict[DocId, float] = defaultdict(float)

        for token in tokens:
            postings_list = self.postings.get(token, [])
            df = len(postings_list)
            for p in postings_list:
                s = scorer.score(
                    doc_id=p.doc_id,
                    tf=p.term_frequency,
                    doc_len=self.doc_lengths.get(p.doc_id, 0),
                    avg_doc_len=self.avg_doc_len,
                    df=df,
                    total_docs=self.total_docs,
                )
                scores[p.doc_id] += s

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:k]
        return [
            SearchResult(
                doc_id=doc_id,
                score=score,
                title=self.doc_titles.get(doc_id, f"Doc {doc_id}"),
                snippet="",
            )
            for doc_id, score in ranked
        ]

    def save(self, filepath: Path) -> None:
        data: dict[str, Any] = {
            "total_docs": self.total_docs,
            "doc_lengths": {str(k): v for k, v in self.doc_lengths.items()},
            "doc_titles": {str(k): v for k, v in self.doc_titles.items()},
            "postings": {
                term: [
                    {"doc_id": p.doc_id, "tf": p.term_frequency, "pos": p.positions}
                    for p in plist
                ]
                for term, plist in self.postings.items()
            },
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        log.info("Saved index to %s (terms=%d, docs=%d)", filepath, len(self.postings), self.total_docs)

    @classmethod
    def load(cls, filepath: Path) -> "InvertedIndex":
        if not filepath.exists():
            raise FileNotFoundError(f"Index file not found: {filepath}")
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        idx = cls()
        idx.total_docs = int(data["total_docs"])
        idx.doc_lengths = {int(k): v for k, v in data["doc_lengths"].items()}
        idx.doc_titles = {int(k): v for k, v in data["doc_titles"].items()}
        for term, plist in data["postings"].items():
            idx.postings[term] = [
                Posting(doc_id=p["doc_id"], term_frequency=p["tf"], positions=p["pos"])
                for p in plist
            ]
        log.info("Loaded index from %s", filepath)
        return idx