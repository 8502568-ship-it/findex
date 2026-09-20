"""Eager vs lazy: `python -m findex.bench data/ --limits 50 200 500` -> Markdown table."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from findex.eager import eager_stats
from findex.stats import lazy_stats, measure


def _mib(n: int) -> str:
    return f"{n / 2**20:.1f} MiB"


def main() -> None:
    parser = argparse.ArgumentParser(prog="findex.bench", description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--limits", type=int, nargs="+", required=True,
                        help="document counts to test, e.g. 50 200 500")
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)

    print("| Version | Documents | Tokens | Peak memory | Elapsed |")
    print("|---|---|---|---|---|")
    for limit in args.limits:
        lazy = measure(lazy_stats, args.root, limit)
        try:
            eager = measure(eager_stats, args.root, limit)
        except MemoryError:
            print(f"| eager (lists) | {limit} | - | MemoryError | - |")
        else:
            assert eager.result == lazy.result, "eager and lazy results differ!"
            r = eager.result
            print(f"| eager (lists) | {r.documents} | {r.tokens} | "
                  f"{_mib(eager.peak_bytes)} | {eager.elapsed:.2f} s |")
        r = lazy.result
        print(f"| lazy (generators) | {r.documents} | {r.tokens} | "
              f"{_mib(lazy.peak_bytes)} | {lazy.elapsed:.2f} s |")


if __name__ == "__main__":
    main()
