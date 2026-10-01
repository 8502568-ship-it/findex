import math
from typing import Protocol, runtime_checkable

from findex.models import DocId


@runtime_checkable
class Scorer(Protocol):
    """Protocol for scoring functions (BM25, TF-IDF)."""

    def score(
        self,
        doc_id: DocId,
        tf: int,
        doc_len: int,
        avg_doc_len: float,
        df: int,
        total_docs: int,
    ) -> float: ...


class BM25Scorer:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def score(
        self,
        doc_id: DocId,
        tf: int,
        doc_len: int,
        avg_doc_len: float,
        df: int,
        total_docs: int,
    ) -> float:
        if tf <= 0 or df <= 0 or total_docs <= 0:
            return 0.0
        # idf standard formula
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
        norm_len = 1.0 - self.b + self.b * (doc_len / avg_doc_len if avg_doc_len > 0 else 1.0)
        num = tf * (self.k1 + 1.0)
        denom = tf + self.k1 * norm_len
        return idf * (num / denom)


class TFIDFScorer:
    def score(
        self,
        doc_id: DocId,
        tf: int,
        doc_len: int,
        avg_doc_len: float,
        df: int,
        total_docs: int,
    ) -> float:
        if tf <= 0 or df <= 0 or total_docs <= 0:
            return 0.0
        tf_weight = 1.0 + math.log(tf)
        idf_weight = math.log(total_docs / df)
        return tf_weight * idf_weight