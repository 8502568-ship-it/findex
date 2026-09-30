"""M2 — Boolean-пошук: двовказівниковий merge та set-альтернатива.

    python -m findex.search index.bin "python dict NOT pickle" --engine merge
Синтаксис: `a b` = a AND b; також AND / OR / NOT (верхній регістр);
обчислення зліва направо, NOT x означає «AND NOT x».
"""
from __future__ import annotations

import argparse
import time
import tracemalloc
from collections.abc import Sequence

from findex.pipeline import tokenize


# ------------------------------ merge-алгоритми ------------------------------
def merge_and(a: Sequence[int], b: Sequence[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    la, lb = len(a), len(b)
    while i < la and j < lb:
        x, y = a[i], b[j]
        if x == y:
            out.append(x); i += 1; j += 1
        elif x < y:
            i += 1
        else:
            j += 1
    return out


def merge_or(a: Sequence[int], b: Sequence[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    la, lb = len(a), len(b)
    while i < la and j < lb:
        x, y = a[i], b[j]
        if x == y:
            out.append(x); i += 1; j += 1
        elif x < y:
            out.append(x); i += 1
        else:
            out.append(y); j += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out


def merge_not(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """a \\ b (елементи a, яких немає в b)."""
    i = j = 0
    out: list[int] = []
    la, lb = len(a), len(b)
    while i < la:
        x = a[i]
        while j < lb and b[j] < x:
            j += 1
        if j < lb and b[j] == x:
            i += 1; j += 1
        else:
            out.append(x); i += 1
    return out


# ------------------------------ set-альтернатива -----------------------------
def set_and(a, b): return sorted(set(a) & set(b))
def set_or(a, b): return sorted(set(a) | set(b))
def set_not(a, b): return sorted(set(a) - set(b))


ENGINES = {
    "merge": (merge_and, merge_or, merge_not),
    "set": (set_and, set_or, set_not),
}


# ------------------------------ парсер + виконання ---------------------------
def parse(query: str) -> list[tuple[str, str]]:
    """-> список (оператор, термін); перший оператор — 'AND' (або 'NOT')."""
    out: list[tuple[str, str]] = []
    op = "AND"
    for word in query.split():
        if word in {"AND", "OR", "NOT"}:
            op = word  # «a OR NOT b» не підтримуємо: NOT = AND NOT
            continue
        for tok in tokenize(word):
            out.append((op, tok))
            op = "AND"
    return out


def evaluate(idx, query: str, engine: str = "merge") -> list[int]:
    f_and, f_or, f_not = ENGINES[engine]
    acc: Sequence[int] | None = None
    for op, term in parse(query):
        ids = idx.doc_ids(term)
        if acc is None:
            acc = f_not(idx.all_doc_ids() if hasattr(idx, "all_doc_ids") else [], ids) \
                if op == "NOT" else ids
        elif op == "AND":
            acc = f_and(acc, ids)
        elif op == "OR":
            acc = f_or(acc, ids)
        else:  # NOT
            acc = f_not(acc, ids)
    return list(acc) if acc is not None else []


def main(argv=None) -> None:
    from findex.store import load

    ap = argparse.ArgumentParser(prog="findex.search")
    ap.add_argument("index")
    ap.add_argument("query")
    ap.add_argument("--engine", choices=["merge", "set"], default="merge")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args(argv)

    tracemalloc.start()
    t0 = time.perf_counter()
    idx = load(a.index)
    t_load = time.perf_counter() - t0
    t1 = time.perf_counter()
    hits = evaluate(idx, a.query, a.engine)
    t_q = time.perf_counter() - t1
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    for d in hits[: a.limit]:
        m = idx.doc_meta[d]
        print(f"[{d}] {m.title}  ({m.path})")
    if len(hits) > a.limit:
        print(f"... ще {len(hits) - a.limit}")
    print(f"\n{len(hits)} документів | load {t_load*1000:.1f} ms, "
          f"query {t_q*1000:.2f} ms ({a.engine}) | peak {peak/2**20:.1f} MiB")


if __name__ == "__main__":
    main()
