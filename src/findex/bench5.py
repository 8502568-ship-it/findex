"""Бенчмарк Лаби 5: wall / CPU / пік RSS / merge для serial, threads, processes.

    uv run python -m findex.bench5 data/gutenberg --repeats 3
    uv run python -m findex.bench5 data/gutenberg --label cpython-3.13t \\
        --python-exe .venv-313t/Scripts/python.exe --executors threads

Кожен замір — окремий новий процес Python (`--one`): так пік RSS і CPU-час
чисті, без «спадку» попередніх запусків. Результати дописуються в
results_lab5.json під ключем --label (повторний запуск іншого інтерпретатора
додає рядки, а не затирає файл).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from findex.parallel import ExecutorKind, build_index, list_corpus


def peak_rss_bytes() -> int:
    """Пік resident set поточного процесу (Windows: PeakWorkingSetSize)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize)

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)  # Linux: KiB


def cpu_model() -> str:
    """Назва процесора (для README)."""
    try:
        if sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        if sys.platform == "linux":
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        if sys.platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            )
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 - довідкове поле, не критично
        pass
    return platform.processor() or "unknown"


def gil_enabled() -> bool:
    return bool(getattr(sys, "_is_gil_enabled", lambda: True)())


def run_one(corpus: Path, executor: ExecutorKind, workers: int, limit: int | None,
            chunks: int | None) -> dict[str, Any]:
    paths = list_corpus(corpus, limit)
    index, stats = build_index(paths, workers=workers, executor=executor, chunks=chunks)
    peak = peak_rss_bytes()
    return {
        "executor": executor,
        "workers": workers,
        "chunks": stats.chunks,
        "wall": stats.wall_seconds,
        "cpu": stats.cpu_seconds,
        "merge": stats.merge_seconds,
        "peak_rss_mib": peak / 2**20,
        "docs": index.total_docs,
        "terms": len(index.postings),
        "postings": sum(len(v) for v in index.postings.values()),
        "python": platform.python_version(),
        "gil_enabled": gil_enabled(),
    }


def orchestrate(args: argparse.Namespace) -> None:
    cores = os.cpu_count() or 1
    worker_counts = sorted({1, 2, 4, 8, cores})
    matrix: list[tuple[str, int]] = []
    for kind in args.executors:
        if kind == "serial":
            matrix.append(("serial", 1))
        else:
            matrix += [(kind, w) for w in worker_counts]

    out_path: Path = args.out
    data: dict[str, Any] = {"meta": {}, "runs": {}}
    if out_path.exists():
        data = json.loads(out_path.read_text(encoding="utf-8"))
    runs: list[dict[str, Any]] = data["runs"].setdefault(args.label, [])

    # прогрів: перший запуск після старту ОС платить за холодний кеш файлів
    if not args.no_warmup:
        print("warm-up run (not recorded)...", flush=True)
        subprocess.run(_cmd(args, "serial", 1), check=True, capture_output=True)

    for kind, workers in matrix:
        for rep in range(args.repeats):
            proc = subprocess.run(_cmd(args, kind, workers), capture_output=True, text=True)
            if proc.returncode != 0:
                sys.exit(f"run failed ({kind} x{workers}):\n{proc.stderr}")
            rec = json.loads(proc.stdout.strip().splitlines()[-1])
            rec["rep"] = rep
            runs.append(rec)
            print(
                f"{args.label:14} {kind:9} x{workers:<2} #{rep + 1}: "
                f"wall {rec['wall']:7.2f}s cpu {rec['cpu']:7.2f}s "
                f"merge {rec['merge']:6.2f}s rss {rec['peak_rss_mib']:7.1f} MiB",
                flush=True,
            )
            # дописуємо після кожного запуску: Ctrl+C не втрачає зроблене
            data["meta"][args.label] = {
                "cpu_model": cpu_model(),
                "cpu_count": cores,
                "platform": platform.platform(),
                "python": rec["python"],
                "gil_enabled": rec["gil_enabled"],
                "docs": rec["docs"],
                "terms": rec["terms"],
            }
            out_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"saved -> {out_path}")


def _cmd(args: argparse.Namespace, kind: str, workers: int) -> list[str]:
    cmd = [args.python_exe, "-m", "findex.bench5", str(args.corpus), "--one",
           "--executor", kind, "--workers", str(workers)]
    if args.limit is not None:
        cmd += ["--limit", str(args.limit)]
    if args.chunks is not None:
        cmd += ["--chunks", str(args.chunks)]
    return cmd


def main() -> None:
    ap = argparse.ArgumentParser(prog="findex.bench5", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--executors", nargs="+", default=["serial", "threads", "processes"],
                    choices=["serial", "threads", "processes"])
    ap.add_argument("--label", default="cpython-3.13", help="ключ у results (напр. cpython-3.13t)")
    ap.add_argument("--python-exe", default=sys.executable,
                    help="інтерпретатор, яким міряти (для 3.13t)")
    ap.add_argument("--out", type=Path, default=Path("results_lab5.json"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--chunks", type=int, default=None, help="фіксувати кількість шматків")
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--one", action="store_true", help="(внутрішній) один замір, JSON у stdout")
    ap.add_argument("--executor", default="serial", choices=["serial", "threads", "processes"])
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()

    if args.one:
        print(json.dumps(run_one(args.corpus, args.executor, args.workers,
                                 args.limit, args.chunks)))
    else:
        orchestrate(args)


if __name__ == "__main__":
    main()
