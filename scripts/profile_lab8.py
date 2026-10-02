from __future__ import annotations

import argparse
import cProfile
import pstats
from pathlib import Path

from findex.index import InvertedIndex


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    parser.add_argument("--query", default="the event loop")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    profiler.enable()
    idx = InvertedIndex.load(args.index)
    idx.search(args.query, args.k, "bm25")
    profiler.disable()
    stats_path = args.out / "search_cprofile.prof"
    profiler.dump_stats(stats_path)
    pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(20)
    print(f"Saved cProfile data to {stats_path}")


if __name__ == "__main__":
    main()
