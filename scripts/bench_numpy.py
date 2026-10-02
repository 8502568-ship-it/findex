from __future__ import annotations

import argparse
import statistics
import time

from findex.index import InvertedIndex
from findex.numpy_search import NumpyIndex


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("index")
    parser.add_argument("--query", default="the event loop")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()

    idx = InvertedIndex.load(__import__("pathlib").Path(args.index))
    np_idx = NumpyIndex.from_index(idx)

    python_times = []
    numpy_times = []
    for _ in range(args.repeats):
        t0 = time.perf_counter()
        idx.search(args.query, args.k)
        python_times.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        np_idx.search(args.query, args.k)
        numpy_times.append((time.perf_counter() - t0) * 1000)

    p = statistics.median(python_times)
    n = statistics.median(numpy_times)
    print(f"query={args.query!r} python={p:.3f}ms numpy={n:.3f}ms speedup={p/n:.2f}x")


if __name__ == "__main__":
    main()
