"""Паралельна побудова індексу (map-reduce): build_partial -> merge.

    map:    кожен воркер будує частковий індекс для свого шматка ШЛЯХІВ до файлів
    reduce: батьківський процес зливає часткові індекси (послідовна частина)

Один і той самий код працює під звичайним циклом, ThreadPoolExecutor і
ProcessPoolExecutor. Процеси запускаються методом spawn (однаково на Windows,
macOS і Linux), тому build_partial — функція рівня модуля, а в воркер ідуть
лише рядки і числа.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from findex.index import InvertedIndex

log = logging.getLogger(__name__)

ExecutorKind = Literal["serial", "threads", "processes"]
DEFAULT_EXECUTOR: ExecutorKind = "serial"  # змінити на "processes", якщо вони виграли
CHUNKS_PER_WORKER = 4  # шматків більше, ніж воркерів: вирівнює навантаження


@dataclass(slots=True)
class Partial:
    """Результат одного воркера: індекс шматка + діапазон doc_id [first_id, end_id)."""

    index: InvertedIndex
    first_id: int
    end_id: int
    cpu_seconds: float  # CPU-час потоку, що виконав шматок


@dataclass(slots=True)
class BuildStats:
    executor: str
    workers: int
    chunks: int
    wall_seconds: float
    cpu_seconds: float  # батьківський процес + (для processes) сума по воркерах
    merge_seconds: float


def list_corpus(corpus_dir: Path, limit: int | None = None) -> list[str]:
    """Той самий порядок, що в Лабі 4: sorted(glob('*.txt')) і --limit."""
    files = sorted(Path(corpus_dir).glob("*.txt"))
    if limit is not None:
        files = files[:limit]
    return [str(p) for p in files]


def build_partial(
    paths: Sequence[str], first_id: int, positions: bool = False
) -> Partial:
    """Індексує шматок: файл paths[i] отримує doc_id = first_id + i.

    Діапазон видано наперед, тому doc_id унікальні на весь корпус і збігаються з
    нумерацією послідовної збірки. Нечитабельний файл пропускається (id
    лишається зарезервованим) — як у Лабі 4; решта винятків летить нагору.
    """
    cpu0 = time.thread_time()
    idx = InvertedIndex()
    for offset, raw in enumerate(paths):
        path = Path(raw)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.warning("Failed to read %s: %s", path, exc)
            continue
        idx.add_document(
            doc_id=first_id + offset,
            title=path.name,
            text=text,
            store_positions=positions,
        )
    return Partial(idx, first_id, first_id + len(paths), time.thread_time() - cpu0)


def merge(partials: Sequence[Partial]) -> InvertedIndex:
    """Зливає часткові індекси в один (послідовний крок: межа за законом Амдала).

    Шматки беруться за зростанням first_id, тож постінги кожного терміна
    лишаються відсортованими за doc_id без додаткового sort. Порядок термінів
    у словнику теж збігається з послідовною збіркою (порядок першої появи).
    """
    out = InvertedIndex()
    prev_end = -1
    for part in sorted(partials, key=lambda p: p.first_id):
        if part.first_id < prev_end:
            raise ValueError(
                f"overlapping doc_id ranges: {part.first_id} < {prev_end}"
            )
        prev_end = part.end_id
        src = part.index
        out.doc_lengths.update(src.doc_lengths)
        out.doc_titles.update(src.doc_titles)
        out.total_docs += src.total_docs
        for term, plist in src.postings.items():
            out.postings[term].extend(plist)
    return out


def plan_chunks(paths: Sequence[str], n_chunks: int) -> list[tuple[int, list[str]]]:
    """Ріже відсортований список на неперервні шматки зі схожою сумою розмірів.

    Повертає [(first_id, paths_slice), ...]; кожен шматок непорожній.
    """
    n = len(paths)
    if n == 0:
        return []
    n_chunks = max(1, min(n_chunks, n))
    sizes: list[int] = []
    for p in paths:
        try:
            sizes.append(max(os.path.getsize(p), 1))
        except OSError:
            sizes.append(1)
    total = sum(sizes)
    chunks: list[tuple[int, list[str]]] = []
    start = acc = 0
    for i, size in enumerate(sizes):
        acc += size
        made = len(chunks)
        if made >= n_chunks - 1:
            continue
        files_left = n - (i + 1)
        chunks_left = n_chunks - made - 1
        if acc >= total * (made + 1) / n_chunks or files_left == chunks_left:
            chunks.append((start, list(paths[start : i + 1])))
            start = i + 1
    chunks.append((start, list(paths[start:])))
    return chunks


def make_executor(kind: ExecutorKind, workers: int) -> Executor:
    if kind == "threads":
        return ThreadPoolExecutor(max_workers=workers, thread_name_prefix="findex")
    if kind == "processes":
        # spawn явно: однакова поведінка на всіх ОС, без успадкування стану батька
        ctx = multiprocessing.get_context("spawn")
        return ProcessPoolExecutor(max_workers=workers, mp_context=ctx)
    raise ValueError(f"no pool for executor {kind!r}")


WorkerFn = Callable[[Sequence[str], int, bool], Partial]


def build_index(
    paths: Sequence[str],
    *,
    workers: int = 1,
    executor: ExecutorKind = "serial",
    positions: bool = False,
    chunks: int | None = None,
    worker: WorkerFn = build_partial,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[InvertedIndex, BuildStats]:
    """Будує індекс обраним виконавцем. Помилка воркера валить усю збірку.

    `worker` можна підмінити (для тестів падіння); під processes це має бути
    функція рівня модуля.
    """
    if workers < 1:
        raise ValueError("workers must be >= 1")
    wall0, cpu0 = time.perf_counter(), time.process_time()
    if chunks is None:
        chunks = 1 if executor == "serial" or workers == 1 else workers * CHUNKS_PER_WORKER
    plan = plan_chunks(paths, chunks)
    partials: list[Partial] = []

    if executor == "serial" or not plan:
        for first_id, chunk in plan:
            partials.append(worker(chunk, first_id, positions))
            if on_progress:
                on_progress(len(partials), len(plan))
    else:
        pool = make_executor(executor, workers)
        try:
            futures = [pool.submit(worker, chunk, first, positions) for first, chunk in plan]
            for fut in as_completed(futures):
                partials.append(fut.result())  # тут піднімається виняток воркера
                if on_progress:
                    on_progress(len(partials), len(plan))
        except BaseException:
            # не чекаємо решту черги; стек воркера вже в __cause__ винятку
            pool.shutdown(wait=True, cancel_futures=True)
            raise
        pool.shutdown(wait=True)

    merge0 = time.perf_counter()
    index = merge(partials)
    merge_s = time.perf_counter() - merge0

    cpu = time.process_time() - cpu0
    if executor == "processes":  # CPU воркерів не входить у process_time батька
        cpu += sum(p.cpu_seconds for p in partials)
    stats = BuildStats(
        executor=executor,
        workers=workers,
        chunks=len(plan),
        wall_seconds=time.perf_counter() - wall0,
        cpu_seconds=cpu,
        merge_seconds=merge_s,
    )
    return index, stats
