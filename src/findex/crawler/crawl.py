from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .fetch import FetchResult, fetch
from .robots import RobotsCache

log = logging.getLogger("findex.crawl")


@dataclass(frozen=True, slots=True)
class Page:
    url: str
    title: str
    text: str
    fetched_at: str
    status: int
    num_bytes: int


@dataclass(slots=True)
class CrawlStats:
    pages: int = 0
    errors: int = 0
    in_flight: int = 0
    peak_in_flight: int = 0
    queue_depth: int = 0
    started: float = field(default_factory=time.perf_counter)

    @property
    def pages_per_second(self) -> float:
        elapsed = max(1e-9, time.perf_counter() - self.started)
        return self.pages / elapsed


def canonicalize(url: str) -> str:
    p = urlsplit(url)
    scheme = p.scheme.lower()
    host = p.hostname.lower() if p.hostname else ""
    if scheme not in {"http", "https"} or not host:
        raise ValueError(f"absolute HTTP(S) URL required: {url}")
    port = p.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = p.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)), doseq=True)
    return urlunsplit((scheme, host, path, query, ""))


class _HTML(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        elif tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                try:
                    self.links.append(canonicalize(urljoin(self.base_url, href)))
                except ValueError:
                    pass

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        if data.strip():
            self.text_parts.append(data.strip())

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split())

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


def _parse_html(url: str, content: bytes) -> tuple[str, str, list[str]]:
    parser = _HTML(url)
    parser.feed(content.decode("utf-8", errors="replace"))
    return parser.title, parser.text, list(dict.fromkeys(parser.links))


async def crawl(
    seeds: Iterable[str],
    *,
    max_pages: int,
    concurrency: int = 10,
    per_host: int = 2,
    host_delay: float = 0.1,
    allowed_domains: set[str] | None = None,
    timeout: float = 10.0,
    user_agent: str = (
        "findex-lab06/1.0 (+https://github.com/8502568-ship-it/findex)"
    ),
    client: httpx.AsyncClient | None = None,
    stats: CrawlStats | None = None,
) -> AsyncIterator[Page]:
    """Queue frontier + TaskGroup workers; yields pages as they arrive."""
    if max_pages < 1 or concurrency < 1 or per_host < 1:
        raise ValueError("max_pages, concurrency and per_host must be positive")
    own_client = client is None
    http = client or httpx.AsyncClient(
        headers={"User-Agent": user_agent}, follow_redirects=True
    )
    metrics = stats or CrawlStats()
    frontier: asyncio.Queue[str] = asyncio.Queue()
    results: asyncio.Queue[Page] = asyncio.Queue()
    seen: set[str] = set()
    state_lock = asyncio.Lock()
    exhausted = asyncio.Event()
    global_sem = asyncio.Semaphore(concurrency)
    host_sems: dict[str, asyncio.Semaphore] = {}
    host_locks: dict[str, asyncio.Lock] = {}
    host_last: dict[str, float] = {}
    pending = 0
    domains = {d.lower().rstrip(".") for d in allowed_domains} if allowed_domains else None

    def domain_ok(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        return domains is None or host in domains or any(
            host.endswith("." + d) for d in domains
        )

    async def enqueue(url: str) -> None:
        nonlocal pending
        try:
            url = canonicalize(url)
        except ValueError:
            return
        if not domain_ok(url):
            return
        async with state_lock:
            if url in seen or len(seen) >= max_pages:
                return
            seen.add(url)
            pending += 1
            await frontier.put(url)
            metrics.queue_depth = frontier.qsize()

    for seed in seeds:
        await enqueue(seed)

    async def mark_done() -> None:
        nonlocal pending
        async with state_lock:
            pending -= 1
            metrics.queue_depth = frontier.qsize()
            if pending == 0:
                exhausted.set()

    async def polite_fetch(url: str) -> FetchResult:
        host = (urlsplit(url).hostname or "").lower()
        sem = host_sems.setdefault(host, asyncio.Semaphore(per_host))
        lock = host_locks.setdefault(host, asyncio.Lock())
        async with global_sem, sem:
            async with lock:
                delay = host_delay - (
                    time.monotonic() - host_last.get(host, 0.0)
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                host_last[host] = time.monotonic()
            metrics.in_flight += 1
            metrics.peak_in_flight = max(metrics.peak_in_flight, metrics.in_flight)
            try:
                return await fetch(http, url, timeout=timeout)
            finally:
                metrics.in_flight -= 1

    robots = RobotsCache(
        http, user_agent=user_agent, timeout=timeout, fetcher=polite_fetch
    )

    async def worker() -> None:
        while True:
            url = await frontier.get()
            metrics.queue_depth = frontier.qsize()
            try:
                if metrics.pages >= max_pages:
                    continue
                if not await robots.allowed(url):
                    log.info(
                        "url=%s status=ROBOTS_DENIED bytes=0 elapsed=0.000s", url
                    )
                    continue
                result = await polite_fetch(url)
                if result.status != 200:
                    metrics.errors += 1
                    continue
                title, text, links = _parse_html(url, result.content)
                metrics.pages += 1
                await results.put(
                    Page(
                        url=url,
                        title=title,
                        text=text,
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                        status=result.status,
                        num_bytes=result.num_bytes,
                    )
                )
                if metrics.pages < max_pages:
                    for link in links:
                        await enqueue(link)
            except asyncio.CancelledError:
                raise
            except Exception:
                metrics.errors += 1
                log.exception("url=%s status=WORKER_ERROR", url)
            finally:
                await mark_done()

    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(worker(), name=f"crawl-worker-{i}")
                for i in range(concurrency)
            ]
            while True:
                if metrics.pages >= max_pages and results.empty():
                    break
                if exhausted.is_set() and results.empty():
                    break
                try:
                    page = await asyncio.wait_for(results.get(), timeout=0.05)
                except TimeoutError:
                    continue
                yield page
                results.task_done()
            for task in tasks:
                task.cancel()
    finally:
        if own_client:
            await http.aclose()
