"""Lazy stats pipeline: `python -m findex.stats data/ [--limit N] [--top 50]`."""

from __future__ import annotations

import argparse
import logging
import time
import tracemalloc
from collections import Counter
from collections.abc import Callable
from itertools import islice
from pathlib import Path
from typing import NamedTuple

from findex.corpus import iter_documents
from findex.tokenize import tokenize


class Stats(NamedTuple):
    documents: int
    tokens: int
    vocabulary: int
    top: list[tuple[str, int]]


class Measurement(NamedTuple):
    result: Stats
    elapsed: float  # seconds
    peak_bytes: int


def lazy_stats(root: Path, limit: int | None = None, top_n: int = 50) -> Stats:
    """Single pass, constant memory: only the Counter (the sink) grows."""
    docs = islice(iter_documents(root), limit)  # limit=None -> everything
    counts: Counter[str] = Counter()
    n_docs = 0
    for doc in docs:
        n_docs += 1
        counts.update(tokenize(doc.text))
    return Stats(n_docs, counts.total(), len(counts), counts.most_common(top_n))


def measure(fn: Callable[..., Stats], *args, **kwargs) -> Measurement:
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return Measurement(result, elapsed, peak)


def main() -> None:
    parser = argparse.ArgumentParser(prog="findex.stats", description=__doc__)
    parser.add_argument("root", type=Path, help="directory with .txt files or a .jsonl file")
    parser.add_argument("--limit", type=int, default=None, help="only the first N documents")
    parser.add_argument("--top", type=int, default=50, help="how many top terms to print")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    m = measure(lazy_stats, args.root, args.limit, args.top)
    s = m.result
    print(f"Documents:   {s.documents}")
    print(f"Tokens:      {s.tokens}")
    print(f"Vocabulary:  {s.vocabulary}")
    print(f"Elapsed:     {m.elapsed:.2f} s")
    print(f"Peak memory: {m.peak_bytes / 2**20:.1f} MiB (tracemalloc)")
    print(f"\nTop {args.top} terms:")
    for rank, (term, n) in enumerate(s.top, start=1):
        print(f"{rank:>4}. {term:<20} {n}")


if __name__ == "__main__":
    main()
