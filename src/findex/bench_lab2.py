"""Усі вимірювання Лаби 2 одним запуском (результат -> results.json + results.md).

    uv run python -m findex.bench_lab2 data/gutenberg --limit 50

Рекомендація: --limit 50 (під tracemalloc усе працює повільно, див. Лабу 1).
Запускай на тому ж корпусі/машині, що й решту лаби.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import tempfile
import time
import tracemalloc
from itertools import islice

from findex.index import build_index
from findex.models import PlainPosting, Posting
from findex.pipeline import iter_docs
from findex.search import ENGINES
from findex.store import load, save


def _build(data, variant, positions=False, limit=None):
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    idx = build_index(islice(iter_docs(data), limit), variant, positions)
    t = time.perf_counter() - t0
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return idx, cur, peak, t


def _timeit(fn, repeat=5):
    best = float("inf")
    for _ in range(repeat):
        t = time.perf_counter(); fn(); best = min(best, time.perf_counter() - t)
    return best


def run(data, limit):
    tmp = tempfile.mkdtemp()
    mib = lambda b: b / 2**20
    R = {"python": sys.version.split()[0], "limit": limit, "memory": [],
         "formats": [], "merge_set": [], "positions": []}

    a, b = PlainPosting(1000, 1000), Posting(1000, 1000)
    R["sizes"] = {"plain_obj": sys.getsizeof(a),
                  "plain_dict": sys.getsizeof(getattr(a, "__dict__", {})),
                  "slots_obj": sys.getsizeof(b), "int": sys.getsizeof(1000),
                  "array_item": 8}

    slots_idx = array_idx = None
    for name, variant in [("list[Posting], звичайний @dataclass", "plain"),
                          ("list[Posting], slots=True", "slots"),
                          ("array('I') пари", "array")]:
        print(f"[M4] {variant}...", file=sys.stderr)
        idx, cur, peak, t_build = _build(data, variant, False, limit)
        p = os.path.join(tmp, f"{variant}.pkl")
        save(idx, p, "pickle")
        t_load = _timeit(lambda p=p: load(p), 3) * 1000
        R["memory"].append({"name": name, "variant": variant,
                            "current_mib": mib(cur), "peak_mib": mib(peak),
                            "build_s": t_build, "file_mib": mib(os.path.getsize(p)),
                            "load_ms": t_load})
        if variant == "slots":
            slots_idx = idx
            R["n_docs"], R["n_terms"] = idx.n_docs, len(idx.terms())
            R["n_postings"] = sum(idx.df(t) for t in idx.terms())
            base_cur, base_peak = cur, peak
        elif variant == "array":
            array_idx = idx
        else:
            del idx
    gc.collect()

    print("[M3] формати...", file=sys.stderr)
    for fmt, idx in [("pickle", slots_idx), ("json", slots_idx), ("binary", array_idx)]:
        p = os.path.join(tmp, "x." + fmt)
        t_save = _timeit(lambda idx=idx, p=p, fmt=fmt: save(idx, p, fmt), 3) * 1000
        def _l(p=p):
            r = load(p)
            if hasattr(r, "close"):
                r.close()
        t_load = _timeit(_l, 3) * 1000
        R["formats"].append({"name": fmt, "file_mib": mib(os.path.getsize(p)),
                             "save_ms": t_save, "load_ms": t_load})

    print("[merge vs set]...", file=sys.stderr)
    by_df = sorted(array_idx.terms(), key=array_idx.df)
    rare, common = by_df[:2], by_df[-2:]
    for label, (x, y) in [("2 найчастіших", common), ("2 найрідкісніших", rare),
                          ("найчастіший + найрідкісніший", (common[-1], rare[0]))]:
        A, B = list(array_idx.doc_ids(x)), list(array_idx.doc_ids(y))
        res = {}
        for eng, (f_and, _, _) in ENGINES.items():
            reps = 300 if len(A) + len(B) < 2000 else 30
            res[eng] = _timeit(lambda f_and=f_and, A=A, B=B: f_and(A, B), reps) * 1e6
        R["merge_set"].append({"label": label, "x": x, "dx": len(A), "y": y,
                               "dy": len(B), "merge_us": res["merge"],
                               "set_us": res["set"]})

    print("[positions]...", file=sys.stderr)
    R["positions"].append({"flag": False, "current_mib": mib(base_cur),
                           "peak_mib": mib(base_peak),
                           "file_mib": R["memory"][1]["file_mib"]})
    idx, cur, peak, _ = _build(data, "slots", True, limit)
    p = os.path.join(tmp, "pos.pkl"); save(idx, p, "pickle")
    R["positions"].append({"flag": True, "current_mib": mib(cur), "peak_mib": mib(peak),
                           "file_mib": mib(os.path.getsize(p))})
    return R


def to_markdown(R) -> str:
    L = [f"Python {R['python']}, документів: {R['n_docs']}, термінів: {R['n_terms']}, "
         f"постінгів: {R['n_postings']}\n", "## M4",
         "| Представлення | В пам'яті після збірки, МіБ | Пік (build), МіБ | Файл (pickle), МіБ | Load, мс |",
         "|---|---|---|---|---|"]
    for r in R["memory"]:
        L.append(f"| {r['name']} | {r['current_mib']:.1f} | {r['peak_mib']:.1f} | "
                 f"{r['file_mib']:.2f} | {r['load_ms']:.0f} |")
    L += ["\n## M3", "| Формат | Файл, МіБ | Save, мс | Load, мс |", "|---|---|---|---|"]
    for r in R["formats"]:
        L.append(f"| {r['name']} | {r['file_mib']:.2f} | {r['save_ms']:.0f} | {r['load_ms']:.1f} |")
    L += ["\n## merge vs set", "| Пара | Терміни (df) | merge, мкс | set, мкс |", "|---|---|---|---|"]
    for r in R["merge_set"]:
        L.append(f"| {r['label']} | {r['x']} ({r['dx']}), {r['y']} ({r['dy']}) | "
                 f"{r['merge_us']:.1f} | {r['set_us']:.1f} |")
    L += ["\n## positions", "| positions | В пам'яті, МіБ | Пік, МіБ | Файл, МіБ |", "|---|---|---|---|"]
    for r in R["positions"]:
        L.append(f"| {r['flag']} | {r['current_mib']:.1f} | {r['peak_mib']:.1f} | {r['file_mib']:.2f} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--limit", type=int, default=None, help="перші N документів")
    ap.add_argument("--out", default="results")
    a = ap.parse_args(argv)
    R = run(a.data, a.limit)
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    md = to_markdown(R)
    with open(a.out + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
