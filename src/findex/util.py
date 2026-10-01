"""Допоміжні декоратори (Лаба 3, M4)."""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger("findex")


def timed(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Логує час виконання у мс (рівень DEBUG).

    Якщо `fn` — це `functools.lru_cache`-обгортка, додатково пише, чи був
    виклик влучанням у кеш, і прокидає `cache_info` / `cache_clear` назовні
    (wraps копіює лише __dict__, а ці методи живуть на типі).
    """

    @functools.wraps(fn)  # без цього search.__name__ == "wrapper", а docstring зникає
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        info = getattr(fn, "cache_info", None)
        hits_before = info().hits if info else 0
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            ms = (time.perf_counter() - t0) * 1000
            tag = ""
            if info:
                tag = " [cache hit]" if info().hits > hits_before else " [cache miss]"
            log.debug("%s took %.3f ms%s", fn.__name__, ms, tag)

    if hasattr(fn, "cache_info"):
        wrapper.cache_info = fn.cache_info  # type: ignore[attr-defined]
        wrapper.cache_clear = fn.cache_clear  # type: ignore[attr-defined]
    return wrapper
