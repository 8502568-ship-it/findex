"""Досліди до Лаби 5: GIL, гонитва даних, ввід-вивід.

    uv run python scripts/gil_demo.py                 # звичайний CPython
    uv run --python 3.13t python scripts/gil_demo.py  # без GIL
    python scripts/gil_demo.py cpu race io            # лише обрані досліди
    python scripts/gil_demo.py --save docs/gil_demo_gil.txt   # ще й у файл (UTF-8)

Кожен дослід друкує версію Python і sys._is_gil_enabled(), щоб у виводі було
видно, на якій збірці він отримані.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def gil_enabled() -> bool:
    return bool(getattr(sys, "_is_gil_enabled", lambda: True)())


def header() -> None:
    print(f"Python {sys.version.split()[0]}  sys._is_gil_enabled() = {gil_enabled()}")
    print(f"switch interval = {sys.getswitchinterval()} s\n")


# ------------------------------- 1. CPU-bound -------------------------------
def burn(n: int = 3_000_000) -> int:
    return sum(i * i for i in range(n))


def timed(fn, *a) -> float:
    t0 = time.perf_counter()
    fn(*a)
    return time.perf_counter() - t0


def exp_cpu() -> None:
    print("== 1. CPU-bound: sum(i*i) ==")
    one = timed(burn)
    print(f"  1 виклик:                 {one:6.2f} s")
    seq = timed(lambda: (burn(), burn()))
    print(f"  2 виклики послідовно:     {seq:6.2f} s")

    def two_threads() -> None:
        ts = [threading.Thread(target=burn) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

    thr = timed(two_threads)
    print(f"  2 виклики у 2 потоках:    {thr:6.2f} s   (x{seq / thr:.2f} до послідовних)")


# --------------------------------- 2. гонитва --------------------------------
N_ITER = 200_000
N_THREADS = 8
shared_int = 0
shared_counter: Counter[str] = Counter()
lock = threading.Lock()


def unsafe_int() -> None:
    global shared_int
    for _ in range(N_ITER):
        shared_int += 1  # LOAD, ADD, STORE: перемикання між ними губить приріст


def unsafe_counter() -> None:
    for _ in range(N_ITER):
        shared_counter["k"] += 1  # читання, додавання, запис: теж не атомарно


def locked_counter() -> None:
    for _ in range(N_ITER):
        with lock:
            shared_counter["k"] += 1


def private_then_merge(results: list[Counter[str]]) -> None:
    local: Counter[str] = Counter()  # фікс без блокувань: нічого не ділимо
    for _ in range(N_ITER):
        local["k"] += 1
    results.append(local)


def run_threads(target, *args) -> None:
    ts = [threading.Thread(target=target, args=args) for _ in range(N_THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


def exp_race() -> None:
    global shared_int
    expected = N_ITER * N_THREADS
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # частіші перемикання: гонитву видно і під GIL
    try:
        print(f"== 2. Гонитва: {N_THREADS} потоків x {N_ITER} інкрементів, очікується {expected} ==")
        shared_int = 0
        run_threads(unsafe_int)
        print(f"  int без блокування:       {shared_int:>9}  втрачено {expected - shared_int}")
        shared_counter.clear()
        run_threads(unsafe_counter)
        print(f"  Counter без блокування:   {shared_counter['k']:>9}  втрачено {expected - shared_counter['k']}")
        shared_counter.clear()
        run_threads(locked_counter)
        print(f"  Counter + Lock:           {shared_counter['k']:>9}  втрачено {expected - shared_counter['k']}")
        parts: list[Counter[str]] = []
        run_threads(private_then_merge, parts)
        total = sum((c["k"] for c in parts))
        print(f"  локальні Counter + merge: {total:>9}  втрачено {expected - total}")
    finally:
        sys.setswitchinterval(old)
    print("  (0 втрат без блокування не доводить коректності: гонитва ймовірнісна, спробуй збільшити N_ITER)")


# ------------------------------ 3. ввід-вивід --------------------------------
def fake_io(_: int) -> None:
    time.sleep(0.05)  # МОДЕЛЬ очікування мережі/диска: GIL під час sleep відпущено


def exp_io() -> None:
    n = 40
    print(f"== 3. Імітація I/O: {n} задач по 50 мс очікування (time.sleep, не реальна мережа) ==")
    serial = timed(lambda: [fake_io(i) for i in range(n)])
    print(f"  послідовно:               {serial:6.2f} s")
    for w in (4, 8, 20):
        def run(w=w) -> None:
            with ThreadPoolExecutor(max_workers=w) as pool:
                list(pool.map(fake_io, range(n)))

        t = timed(run)
        print(f"  потоки x{w:<2}:               {t:6.2f} s   (прискорення x{serial / t:.1f})")


EXPERIMENTS = {"cpu": exp_cpu, "race": exp_race, "io": exp_io}


class Tee:
    """Пише і в консоль, і у файл (UTF-8 незалежно від кодування PowerShell)."""

    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, s: str) -> int:
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self) -> None:
        for st in self.streams:
            st.flush()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = sys.argv[1:]
    save = None
    if "--save" in args:
        i = args.index("--save")
        save = args[i + 1]
        del args[i : i + 2]
    f = open(save, "w", encoding="utf-8") if save else None
    if f:
        sys.stdout = Tee(sys.__stdout__, f)  # type: ignore[assignment]
    header()
    for name in args or EXPERIMENTS:
        EXPERIMENTS[name]()
        print()
    if f:
        sys.stdout = sys.__stdout__  # інакше Tee.flush() при виході писатиме в закритий файл
        f.close()
