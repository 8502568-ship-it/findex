from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    index = (len(values) - 1) * p / 100
    lo, hi = int(index), min(int(index) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


async def run_async(url: str, n: int) -> list[float]:
    async with httpx.AsyncClient() as client:
        async def one() -> float:
            start = time.perf_counter()
            r = await client.get(url, params={"q": "asyncio", "k": 5})
            r.raise_for_status()
            return time.perf_counter() - start
        return await asyncio.gather(*(one() for _ in range(n)))


def run_sync(url: str, n: int) -> list[float]:
    def one() -> float:
        start = time.perf_counter()
        with httpx.Client() as client:
            r = client.get(url, params={"q": "asyncio", "k": 5})
            r.raise_for_status()
        return time.perf_counter() - start
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(lambda _: one(), range(n)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", default="http://127.0.0.1:8000/search", nargs="?")
    ap.add_argument("--requests", type=int, default=20)
    ap.add_argument("--mode", choices=["async", "def"], default="async")
    args = ap.parse_args()
    start = time.perf_counter()
    values = asyncio.run(run_async(args.url, args.requests)) if args.mode == "async" else run_sync(args.url, args.requests)
    elapsed = time.perf_counter() - start
    print(f"mode={args.mode} requests={len(values)} rps={len(values)/elapsed:.2f} p50={percentile(values,50)*1000:.2f}ms p95={percentile(values,95)*1000:.2f}ms p99={percentile(values,99)*1000:.2f}ms")


if __name__ == "__main__":
    main()
