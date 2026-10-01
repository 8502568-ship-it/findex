"""Лаба 5: build_partial/merge, три виконавці, падіння воркера, CLI-прапорці."""

from __future__ import annotations

import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from findex.cli import app
from findex.index import InvertedIndex
from findex.parallel import (
    ExecutorKind,
    Partial,
    build_index,
    build_partial,
    list_corpus,
    merge,
    plan_chunks,
)

runner = CliRunner()

WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu".split()


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """14 файлів різного розміру + один із биттим UTF-8 (його всі режими пропускають)."""
    d = tmp_path_factory.mktemp("lab5_corpus")
    for i in range(14):
        body = " ".join(WORDS[(i + j) % len(WORDS)] for j in range(40 * (i + 1)))
        (d / f"doc{i:02d}.txt").write_text(f"Doc {i} {body} unique{i}", encoding="utf-8")
    (d / "doc07_bad.txt").write_bytes(b"ok words \xff\xfe broken bytes")
    return d


def lab4_index(paths: Sequence[str], positions: bool = False) -> InvertedIndex:
    """Еталон: цикл з `findex index` у Лабі 4 (один процес, enumerate)."""
    idx = InvertedIndex()
    for doc_id, p in enumerate(paths):
        try:
            text = Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        idx.add_document(doc_id=doc_id, title=Path(p).name, text=text,
                         store_positions=positions)
    return idx


def snapshot(idx: InvertedIndex) -> tuple[Any, ...]:
    """Усе, що входить в індекс, включно з порядком ключів словників."""
    return (
        idx.total_docs,
        list(idx.doc_lengths.items()),
        list(idx.doc_titles.items()),
        [(t, list(pl)) for t, pl in idx.postings.items()],
    )


@pytest.mark.parametrize("positions", [False, True])
def test_serial_merge_equals_lab4(corpus: Path, positions: bool) -> None:
    paths = list_corpus(corpus)
    expected = lab4_index(paths, positions)
    got = merge([build_partial(paths, 0, positions)])
    assert snapshot(got) == snapshot(expected)


def test_chunked_merge_equals_lab4_any_order(corpus: Path) -> None:
    paths = list_corpus(corpus)
    parts = [build_partial(chunk, first) for first, chunk in plan_chunks(paths, 5)]
    assert snapshot(merge(parts)) == snapshot(lab4_index(paths))
    assert snapshot(merge(parts[::-1])) == snapshot(lab4_index(paths))


@pytest.mark.parametrize("n_chunks", [1, 2, 5, 15, 99])
def test_plan_chunks_is_contiguous_partition(corpus: Path, n_chunks: int) -> None:
    paths = list_corpus(corpus)
    plan = plan_chunks(paths, n_chunks)
    assert len(plan) == min(n_chunks, len(paths))
    flat: list[str] = []
    for first_id, chunk in plan:
        assert chunk, "порожній шматок"
        assert first_id == len(flat), "діапазон doc_id має починатися одразу за попереднім"
        flat += chunk
    assert flat == paths


def test_plan_chunks_empty() -> None:
    assert plan_chunks([], 4) == []


def test_merge_rejects_overlapping_ranges(corpus: Path) -> None:
    paths = list_corpus(corpus)[:4]
    a = build_partial(paths, 0)
    b = build_partial(paths, 2)  # діапазон [2, 6) перетинається з [0, 4)
    with pytest.raises(ValueError, match="overlapping"):
        merge([a, b])


@pytest.mark.parametrize("kind", ["serial", "threads", "processes"])
@pytest.mark.parametrize("workers", [1, 3])
def test_all_executors_identical(corpus: Path, kind: ExecutorKind, workers: int) -> None:
    paths = list_corpus(corpus)
    idx, stats = build_index(paths, workers=workers, executor=kind, positions=True)
    assert snapshot(idx) == snapshot(lab4_index(paths, positions=True))
    assert stats.wall_seconds > 0 and stats.cpu_seconds >= 0
    assert 0 <= stats.merge_seconds <= stats.wall_seconds


def test_unreadable_file_is_skipped_in_every_mode(corpus: Path) -> None:
    paths = list_corpus(corpus)
    bad_id = paths.index(str(corpus / "doc07_bad.txt"))
    for kind in ("serial", "threads", "processes"):
        idx, _ = build_index(paths, workers=2, executor=kind)  # type: ignore[arg-type]
        assert bad_id not in idx.doc_lengths
        assert idx.total_docs == len(paths) - 1


# ----------------------------- падіння воркера ------------------------------
def failing_worker(paths: Sequence[str], first_id: int, positions: bool) -> Partial:
    """Функція рівня модуля (picklable). Шматок з першим id > 0 падає."""
    if first_id > 0:
        raise RuntimeError(f"boom in chunk starting at {first_id}")
    return build_partial(paths, first_id, positions)


@pytest.mark.parametrize("kind", ["serial", "threads", "processes"])
def test_worker_failure_fails_the_build_with_traceback(corpus: Path, kind: ExecutorKind) -> None:
    paths = list_corpus(corpus)
    with pytest.raises(RuntimeError, match="boom") as info:
        build_index(paths, workers=2, executor=kind, chunks=4, worker=failing_worker)
    text = "".join(traceback.format_exception(info.value))
    assert "failing_worker" in text, "у виводі має бути стек воркера"


# ---------------------------------- CLI -------------------------------------
@pytest.mark.parametrize("kind", ["threads", "processes"])
def test_cli_parallel_file_equals_serial_file(corpus: Path, tmp_path: Path, kind: str) -> None:
    serial_out, par_out = tmp_path / "s.json", tmp_path / "p.json"
    r1 = runner.invoke(app, ["index", str(corpus), "-o", str(serial_out)])
    r2 = runner.invoke(app, ["index", str(corpus), "-o", str(par_out),
                             "--executor", kind, "--workers", "2"])
    assert r1.exit_code == 0 and r2.exit_code == 0
    assert serial_out.read_bytes() == par_out.read_bytes()  # байт у байт


def test_cli_rejects_zero_workers(corpus: Path, tmp_path: Path) -> None:
    r = runner.invoke(app, ["index", str(corpus), "-o", str(tmp_path / "x.json"),
                            "--workers", "0"])
    assert r.exit_code != 0
