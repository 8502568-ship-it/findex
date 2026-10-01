"""Графік прискорення від числа воркерів + пряма ідеального росту.

    uv run python scripts/plot_lab5.py --results results_lab5.json --out docs/speedup_lab5.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from lab5_data import load, rows  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("results_lab5.json"))
    ap.add_argument("--out", type=Path, default=Path("docs/speedup_lab5.png"))
    args = ap.parse_args()
    data = load(args.results)
    rs = rows(data)

    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=150)
    max_w = max(r["workers"] for r in rs)
    ax.plot([1, max_w], [1, max_w], "k--", lw=1, label="ідеальне лінійне")
    styles = {"threads": "o-", "processes": "s-"}
    for label in data["runs"]:
        for ex in ("threads", "processes"):
            pts = sorted((r["workers"], r["speedup"]) for r in rs
                         if r["label"] == label and r["executor"] == ex)
            if pts:
                xs, ys = zip(*pts)
                ax.plot(xs, ys, styles[ex], label=f"{ex} ({label})")
    ax.axhline(1.0, color="gray", lw=0.6)
    ax.set_xlabel("число воркерів")
    ax.set_ylabel("прискорення відносно serial")
    ax.set_title("findex index: прискорення збірки індексу")
    ax.set_xticks(sorted({r["workers"] for r in rs if r["executor"] != "serial"}))
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out)
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
