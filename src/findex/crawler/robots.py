from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from .fetch import FetchResult, fetch

log = logging.getLogger("findex.crawl.robots")


@dataclass(slots=True)
class _RobotsEntry:
    parser: RobotFileParser


class RobotsCache:
    """Fetch and cache one robots.txt per scheme+host."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        user_agent: str,
        timeout: float = 10.0,
        fetcher: Callable[[str], Awaitable[FetchResult]] | None = None,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._timeout = timeout
        self._fetcher = fetcher
        self._cache: dict[str, _RobotsEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _host_key(url: str) -> str:
        p = urlsplit(url)
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), "", "", ""))

    async def _load(self, host: str) -> _RobotsEntry:
        robots_url = host.rstrip("/") + "/robots.txt"
        if self._fetcher is None:
            result = await fetch(self._client, robots_url, timeout=self._timeout)
        else:
            result = await self._fetcher(robots_url)
        parser = RobotFileParser(robots_url)
        if result.status == 404:
            parser.parse([])
        elif result.status == 200:
            parser.parse(result.content.decode("utf-8", errors="replace").splitlines())
        else:
            parser.parse([f"User-agent: {self._user_agent}", "Disallow: /"])
        entry = _RobotsEntry(parser)
        self._cache[host] = entry
        log.info("robots host=%s status=%s", host, result.status)
        return entry

    async def allowed(self, url: str) -> bool:
        host = self._host_key(url)
        entry = self._cache.get(host)
        if entry is None:
            lock = self._locks.setdefault(host, asyncio.Lock())
            async with lock:
                entry = self._cache.get(host)
                if entry is None:
                    entry = await self._load(host)
        return entry.parser.can_fetch(self._user_agent, url)
