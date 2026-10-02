from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import time

import httpx

from findex.crawler import CrawlStats, crawl


def rss_mib() -> float:
    if os.name != "nt":
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
        ]

    counters = Counters(ctypes.sizeof(Counters))
    ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
        ctypes.windll.kernel32.GetCurrentProcess(),
        ctypes.byref(counters), ctypes.sizeof(counters),
    )
    return counters.peak_working_set_size / (1024 * 1024)


async def run(
    url: str, max_pages: int, concurrency: int, per_host: int
) -> dict[str, float | int]:
    stats = CrawlStats()
    started = time.perf_counter()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        pages = 0
        async for _ in crawl(
            [url], max_pages=max_pages, concurrency=concurrency,
            per_host=per_host, host_delay=0, client=client, stats=stats,
        ):
            pages += 1
    wall = time.perf_counter() - started
    return {
        "concurrency": concurrency, "pages": pages, "wall": wall,
        "pages_per_sec": pages / wall, "errors": stats.errors,
        "peak_in_flight": stats.peak_in_flight, "peak_rss_mib": rss_mib(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--per-host", type=int, default=20)
    parser.add_argument("--concurrency", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(
        run(args.url, args.max_pages, args.concurrency, args.per_host)
    )))


if __name__ == "__main__":
    main()
