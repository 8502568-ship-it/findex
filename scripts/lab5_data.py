"""Спільна обробка results_lab5.json для plot_lab5.py і make_report_lab5.py."""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path
from typing import Any

BASE_LABEL = "cpython-3.13"  # еталон для прискорення: serial на звичайній збірці


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def med(runs: list[dict[str, Any]], key: str) -> float:
    return st.median(r[key] for r in runs)


def rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Медіани по кожній клітинці (label, executor, workers) + прискорення."""
    cells: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for label, runs in data["runs"].items():
        for r in runs:
            cells.setdefault((label, r["executor"], r["workers"]), []).append(r)
    base_label = BASE_LABEL if BASE_LABEL in data["runs"] else next(iter(data["runs"]))
    base = med(cells[(base_label, "serial", 1)], "wall")
    out = []
    for (label, ex, w), rs in cells.items():
        wall = med(rs, "wall")
        out.append({
            "label": label, "executor": ex, "workers": w, "n": len(rs),
            "wall": wall, "wall_min": min(r["wall"] for r in rs),
            "wall_max": max(r["wall"] for r in rs),
            "cpu": med(rs, "cpu"), "rss": med(rs, "peak_rss_mib"),
            "merge": med(rs, "merge"), "speedup": base / wall, "base": base,
            "postings": rs[0]["postings"],
        })
    order = {"serial": 0, "threads": 1, "processes": 2}
    out.sort(key=lambda r: (r["label"] != base_label, r["label"], order[r["executor"]], r["workers"]))
    return out
