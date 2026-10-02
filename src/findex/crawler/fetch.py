from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

log = logging.getLogger("findex.crawl")
SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int | None
    content: bytes
    elapsed: float
    error: str | None = None
    headers: dict[str, str] | None = None

    @property
    def num_bytes(self) -> int:
        return len(self.content)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            dt = email.utils.parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _backoff(attempt: int, retry_after: str | None, base: float, cap: float) -> float:
    retry = _retry_after(retry_after)
    if retry is not None:
        return min(cap, retry)
    return min(cap, base * (2**attempt)) + random.uniform(0.0, 1.0)


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 10.0,
    max_retries: int = 3,
    backoff_base: float = 0.2,
    backoff_cap: float = 5.0,
    sleep: SleepFn = asyncio.sleep,
) -> FetchResult:
    """Fetch one URL with timeout and bounded transient retries."""
    started = time.perf_counter()
    for attempt in range(max_retries + 1):
        try:
            async with asyncio.timeout(timeout):
                response = await client.get(url)
        except TimeoutError as exc:
            elapsed = time.perf_counter() - started
            if attempt < max_retries:
                delay = _backoff(attempt, None, backoff_base, backoff_cap)
                log.warning(
                    "url=%s status=TIMEOUT attempt=%d retry_in=%.2fs",
                    url, attempt + 1, delay,
                )
                await sleep(delay)
                continue
            log.error(
                "url=%s status=TIMEOUT retries_exhausted elapsed=%.3fs",
                url, elapsed,
            )
            return FetchResult(url, None, b"", elapsed, type(exc).__name__)

        elapsed = time.perf_counter() - started
        status = response.status_code
        retryable = status == 429 or 500 <= status <= 599
        if retryable and attempt < max_retries:
            delay = _backoff(
                attempt, response.headers.get("Retry-After"),
                backoff_base, backoff_cap,
            )
            log.warning(
                "url=%s status=%d attempt=%d retry_in=%.2fs",
                url, status, attempt + 1, delay,
            )
            await sleep(delay)
            continue

        content = response.content
        level = logging.ERROR if status >= 400 else logging.INFO
        log.log(
            level,
            "url=%s status=%d bytes=%d elapsed=%.3fs attempts=%d",
            url, status, len(content), elapsed, attempt + 1,
        )
        return FetchResult(
            url, status, content, elapsed, headers=dict(response.headers),
        )

    raise AssertionError("unreachable")
