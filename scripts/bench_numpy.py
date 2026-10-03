from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from findex.index import InvertedIndex
from findex.numpy_search import NumpyIndex


def median_ms(fn, repeats: int) -> float:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def pick_rare_term(index: InvertedIndex) -> str:
    candidates = [
        term
        for term, postings in index.postings.items()
        if len(postings) == 1 and term.isalpha() and len(term) >= 5
    ]
    if not candidates:
        raise RuntimeError(
            "Could not find an alphabetic term with document frequency 1"
        )
    return min(candidates, key=lambda term: (len(term), term))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Python and NumPy scorers on representative queries."
    )
    parser.add_argument("index")
    parser.add_argument("--frequent", default="the")
    parser.add_argument("--rare", default=None)
    parser.add_argument("--query", default="the event loop")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()

    index = InvertedIndex.load(Path(args.index))
    numpy_index = NumpyIndex.from_index(index)
    rare = args.rare or pick_rare_term(index)

    cases = [
        ("frequent", args.frequent),
        ("rare", rare),
        ("3-term", args.query),
    ]

    print("| case | query | scorer | Python ms | NumPy ms | speedup |")
    print("|---|---|---|---:|---:|---:|")
    for case, query in cases:
        for scorer in ("bm25", "tfidf"):
            python_ms = median_ms(
                lambda query=query, scorer=scorer: index.search(
                    query,
                    args.k,
                    scorer_name=scorer,
                ),
                args.repeats,
            )
            numpy_ms = median_ms(
                lambda query=query, scorer=scorer: numpy_index.search(
                    query,
                    args.k,
                    scorer=scorer,
                ),
                args.repeats,
            )
            print(
                f"| {case} | {query!r} | {scorer} | "
                f"{python_ms:.3f} | {numpy_ms:.3f} | {python_ms / numpy_ms:.2f}x |"
            )


if __name__ == "__main__":
    main()
