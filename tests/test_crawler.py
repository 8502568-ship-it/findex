from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from findex.crawler import canonicalize, crawl, fetch
from findex.crawler.robots import RobotsCache


def test_canonicalize_normalizes_components() -> None:
    assert canonicalize("HTTP://Example.COM/a/?b=2&a=1#x") == (
        "http://example.com/a?a=1&b=2"
    )
    assert canonicalize("https://Example.com/") == "https://example.com/"


def test_fetch_retries_429_and_honors_retry_after() -> None:
    async def run() -> None:
        calls = 0
        sleeps: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, content=b"ok")

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch(client, "https://example.test/x", sleep=fake_sleep)
        assert result.status == 200 and result.content == b"ok"
        assert calls == 3 and sleeps == [0.0, 0.0]

    asyncio.run(run())


def test_fetch_retries_timeout_three_times() -> None:
    async def run() -> None:
        calls = 0
        sleeps: list[float] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return httpx.Response(200, content=b"late")

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch(
                client, "https://example.test/slow", timeout=0.001, sleep=fake_sleep
            )
        assert result.status is None
        assert calls == 4 and len(sleeps) == 3

    asyncio.run(run())


def test_fetch_does_not_retry_404() -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(404, content=b"missing")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch(client, "https://example.test/missing")
        assert result.status == 404 and calls == 1

    asyncio.run(run())


def test_robots_cache_is_per_host() -> None:
    async def run() -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(
                    200, content=b"User-agent: *\nDisallow: /private\n"
                )
            return httpx.Response(200, content=b"<p>x</p>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            robots = RobotsCache(client, user_agent="findex-test/1.0")
            assert await robots.allowed("https://one.test/public")
            assert not await robots.allowed("https://one.test/private/x")
            assert await robots.allowed("https://one.test/public/2")
            assert await robots.allowed("https://two.test/public")
        assert calls.count("https://one.test/robots.txt") == 1
        assert calls.count("https://two.test/robots.txt") == 1

    asyncio.run(run())


def test_crawl_streams_pages_and_respects_max_pages() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, content=b"User-agent: *\nAllow: /\n")
            n = int(request.url.path.rsplit("/", 1)[-1])
            body = (
                f"<html><title>{n}</title><body>"
                f"<a href='/page/{n+1}'>next</a></body></html>"
            )
            return httpx.Response(200, content=body.encode())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            pages = [
                p
                async for p in crawl(
                    ["https://example.test/page/0"],
                    max_pages=7,
                    concurrency=3,
                    per_host=2,
                    host_delay=0,
                    client=client,
                )
            ]
        assert len(pages) == 7
        assert len({p.url for p in pages}) == 7

    asyncio.run(run())


def test_debug_has_no_sync_sleep_in_crawler_source() -> None:
    source = Path(__file__).parents[1] / "src/findex/crawler/crawl.py"
    assert "time.sleep(" not in source.read_text()
