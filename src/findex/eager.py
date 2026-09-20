"""The deliberately memory-hungry version (list of docs -> list of token lists -> count)."""

from __future__ import annotations

from collections import Counter
from itertools import islice
from pathlib import Path

from findex.corpus import iter_documents
from findex.stats import Stats
from findex.tokenize import tokenize


def eager_stats(root: Path, limit: int | None = None, top_n: int = 50) -> Stats:
    docs = list(islice(iter_documents(root), limit))  # ALL texts in RAM
    tokenized = [list(tokenize(d.text)) for d in docs]  # ALL tokens in RAM
    counts = Counter(tok for toks in tokenized for tok in toks)
    return Stats(len(docs), counts.total(), len(counts), counts.most_common(top_n))
