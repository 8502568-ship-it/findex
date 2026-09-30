"""M1 — побудова інвертованого індексу одним проходом по лінивому корпусу.

    python -m findex.index data/ --out index.bin
"""
from __future__ import annotations

import argparse
import time
import tracemalloc
from array import array
from collections import Counter, defaultdict
from collections.abc import Iterable

from findex.models import ArrayIndex, DocMeta, ObjectIndex, PlainPosting, Posting
from findex.pipeline import RawDoc, iter_docs, tokenize


def build_index(docs: Iterable[RawDoc], variant: str = "slots",
                positions: bool = False):
    """variant: 'plain' | 'slots' | 'array'.

    Один прохід: для поточного документа збираємо Counter (і позиції),
    в кінці документа «скидаємо» його у глобальний defaultdict. doc_id
    зростають, тому списки постінгів автоматично відсортовані.
    Корпус НЕ матеріалізується — у пам'яті лише індекс.
    """
    if variant not in {"plain", "slots", "array"}:
        raise ValueError(variant)
    cls = PlainPosting if variant == "plain" else Posting
    if variant == "array":
        if positions:
            raise ValueError("variant 'array' не зберігає позиції")
        arr_post: defaultdict[str, tuple[array, array]] = defaultdict(
            lambda: (array("I"), array("I")))
        idx = ArrayIndex()
    else:
        obj_post: defaultdict[str, list] = defaultdict(list)
        idx = ObjectIndex()

    for doc_id, doc in enumerate(docs):
        counts: Counter[str] = Counter()
        pos: defaultdict[str, list[int]] = defaultdict(list)
        n = 0
        for i, tok in enumerate(tokenize(doc.text)):
            counts[tok] += 1
            if positions:
                pos[tok].append(i)
            n += 1
        idx.doc_lengths[doc_id] = n
        idx.doc_meta[doc_id] = DocMeta(doc_id, doc.path, doc.title)
        for term, tf in counts.items():
            if variant == "array":
                ids, tfs = arr_post[term]
                ids.append(doc_id)
                tfs.append(tf)
            elif positions:
                obj_post[term].append(cls(doc_id, tf, tuple(pos[term])))
            else:
                obj_post[term].append(cls(doc_id, tf))

    # defaultdict -> звичайний dict, щоб запит неіснуючого терміна не створював запис
    idx.postings = dict(arr_post if variant == "array" else obj_post)
    return idx


def main(argv=None) -> None:
    from findex.store import save

    ap = argparse.ArgumentParser(prog="findex.index")
    ap.add_argument("data", help="каталог із документами")
    ap.add_argument("--out", default="index.bin")
    ap.add_argument("--format", choices=["pickle", "json", "binary"], default="pickle")
    ap.add_argument("--variant", choices=["plain", "slots", "array"], default=None,
                    help="за замовчуванням: slots (pickle/json) або array (binary)")
    ap.add_argument("--positions", action="store_true", help="зберігати позиції токенів")
    a = ap.parse_args(argv)
    variant = a.variant or ("array" if a.format == "binary" else "slots")

    tracemalloc.start()
    t0 = time.perf_counter()
    idx = build_index(iter_docs(a.data), variant, a.positions)
    t_build = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    t1 = time.perf_counter()
    save(idx, a.out, a.format)
    t_save = time.perf_counter() - t1
    import os
    print(f"docs={idx.n_docs} terms={len(idx.terms())} variant={variant} "
          f"positions={a.positions}")
    print(f"build: {t_build:.2f}s, peak memory: {peak/2**20:.1f} MiB (tracemalloc)")
    print(f"save[{a.format}]: {t_save:.2f}s, file: {os.path.getsize(a.out)/2**20:.2f} MiB")


if __name__ == "__main__":
    main()
