"""Заповнює [X] у чернетці звіту Лаби 2 числами з results.json + генерує README_lab2.md.

    uv run python scripts/make_report.py ^
        --template "Лабораторна2_звіт_чернетка.docx" ^
        --results results.json --out "Лабораторна2_звіт.docx" --readme README_lab2.md

results.json створює `python -m findex.bench_lab2 data/gutenberg --limit 50`.
Чернетка не змінюється; результат пишеться в --out.
"""
from __future__ import annotations

import argparse
import json
import sys

import docx
from docx.oxml.ns import qn

MIB = 2**20


# ----------------------------- форматування ---------------------------------
def f(x: float, d: int = 1) -> str:
    """Число з десятковою комою (як у решті звіту)."""
    return f"{x:.{d}f}".replace(".", ",")


def i(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u00a0")  # нерозривний пробіл як роздільник тисяч


def times(x: float) -> str:
    return f(x, 1)


# ----------------------------- значення -------------------------------------
def derive(R: dict) -> dict:
    m = {r["variant"]: r for r in R["memory"]}
    plain, slots, arr = m["plain"], m["slots"], m["array"]
    n = R["n_postings"]
    bpp = {k: v["current_mib"] * MIB / n for k, v in m.items()}
    fm = {r["name"]: r for r in R["formats"]}
    pos_f, pos_t = R["positions"]
    ms = R["merge_set"]
    for r in ms:
        r["faster"] = "merge" if r["merge_us"] < r["set_us"] else "set"
        r["ratio"] = max(r["merge_us"], r["set_us"]) / min(r["merge_us"], r["set_us"])
    return dict(m=m, plain=plain, slots=slots, arr=arr, n=n, bpp=bpp, fm=fm,
                pos_f=pos_f, pos_t=pos_t, ms=ms)


def merge_set_sentence(ms: list[dict]) -> str:
    parts = [f"{r['label']}: {r['faster']} швидший у ×{times(r['ratio'])}" for r in ms]
    wins = sum(r["faster"] == "merge" for r in ms)
    s = "Підсумок: " + "; ".join(parts) + ". "
    if wins == len(ms):
        s += ("Merge виграв у всіх трьох випадках: на списках такої довжини вигода від "
              "того, що set виконується в C, менша за ціну побудови двох хеш-таблиць "
              "(набір кожного списку в set і сортування результату), а merge лише один "
              "раз проходить по обох списках. ")
    elif wins == 0:
        s += ("Set виграв у всіх випадках: його цикл виконується в C, тоді як merge — "
              "цикл на Python, і накладні витрати інтерпретатора перевищують ціну "
              "побудови хеш-таблиць. ")
    else:
        s += ("Результат залежить від довжини списків: set виконується в C, а merge — "
              "цикл на Python; merge не будує хеш-таблиць і вигідніший, коли списки "
              "короткі або один із них дуже короткий. ")
    return s


def placeholder_values(R: dict, D: dict) -> list[str]:
    m, plain, slots, arr, n, bpp = D["m"], D["plain"], D["slots"], D["arr"], D["n"], D["bpp"]
    fm, pf, pt, ms = D["fm"], D["pos_f"], D["pos_t"], D["ms"]
    S = R["sizes"]
    v: list[str] = []
    # Розділ 5, вступ
    v += [str(R["n_docs"]), i(R["n_terms"]), i(n)]
    # Таблиця 3
    for k in ("plain", "slots", "array"):
        r = m[k]
        v += [f(r["current_mib"]), f(r["peak_mib"]), f(r["file_mib"], 2), f(r["load_ms"], 0)]
    # Таблиця 4
    for k in ("pickle", "json", "binary"):
        r = fm[k]
        v += [f(r["file_mib"], 2), f(r["save_ms"], 0), f(r["load_ms"], 1)]
    # Таблиця 5
    for r in ms:
        v += [r["x"], str(r["dx"]), r["y"], str(r["dy"]),
              f(r["merge_us"]), f(r["set_us"]), r["faster"]]
    # Таблиця 6
    for r in (pf, pt):
        v += [f(r["current_mib"]), f(r["peak_mib"]), f(r["file_mib"], 2)]
    # 6, «Куди пішли байти»
    sl_save = (plain["current_mib"] - slots["current_mib"]) * MIB / n
    v += [f(plain["current_mib"]), f(slots["current_mib"]), f(arr["current_mib"]),
          f(bpp["plain"], 0), f(bpp["slots"], 0), f(bpp["array"], 0),
          times(plain["current_mib"] / slots["current_mib"]),
          times(slots["current_mib"] / arr["current_mib"]),
          times(plain["current_mib"] / arr["current_mib"])]
    # 6, «Розкладання за варіантами»
    v += [str(S["plain_obj"]), str(S["int"]), f(sl_save, 0), str(S["slots_obj"]),
          f(bpp["array"] - 8, 0)]
    # 6, «Пік проти залишку»
    v += [f(r["peak_mib"] - r["current_mib"]) for r in (plain, slots, arr)]
    # 6, «Формати»
    v += [f(fm[k]["file_mib"], 2) for k in ("pickle", "json", "binary")]
    v += [f(fm[k]["load_ms"], 1) for k in ("pickle", "json", "binary")]
    v += [times(fm["pickle"]["load_ms"] / fm["binary"]["load_ms"])]
    # 6, «merge проти set»
    for r in ms:
        v += [f(r["merge_us"]), f(r["set_us"])]
    v += [merge_set_sentence(ms)]  # замінює великий плейсхолдер [X: ...]
    # 6, «Позиції»
    v += [f(pf["current_mib"]), f(pt["current_mib"]), times(pt["current_mib"] / pf["current_mib"]),
          f(pf["file_mib"], 2), f(pt["file_mib"], 2), times(pt["file_mib"] / pf["file_mib"])]
    # 7, питання 5
    v += [f(sl_save, 0)]
    # 7, питання 6
    v += [times(slots["current_mib"] / arr["current_mib"]), f(slots["current_mib"]),
          f(arr["current_mib"]), str(S["slots_obj"]), str(S["int"]), f(bpp["slots"], 0)]
    # 8, висновки
    wins = sum(r["faster"] == "merge" for r in ms)
    v += [str(R["n_docs"]), times(plain["current_mib"] / slots["current_mib"]),
          f(plain["current_mib"]), f(slots["current_mib"]),
          times(slots["current_mib"] / arr["current_mib"]), f(arr["current_mib"]),
          f(fm["binary"]["load_ms"], 1), f(fm["pickle"]["load_ms"], 1), str(wins),
          times(pt["current_mib"] / pf["current_mib"])]
    return v


# ----------------------------- docx ------------------------------------------
def fill(template: str, out: str, values: list[str]) -> None:
    d = docx.Document(template)
    runs = []
    for r in d.element.body.iter(qn("w:r")):
        t = "".join(x.text or "" for x in r.iter(qn("w:t")))
        if t.startswith("[X"):
            runs.append((r, t))
    if len(runs) != len(values):
        sys.exit(f"Плейсхолдерів у чернетці: {len(runs)}, значень: {len(values)}. "
                 "Чернетку змінено — порядок [X] більше не збігається зі скриптом.")
    for (r, t), val in zip(runs, values):
        ts = list(r.iter(qn("w:t")))
        ts[0].text = val
        for extra in ts[1:]:
            extra.getparent().remove(extra)
        rpr = r.find(qn("w:rPr"))
        if rpr is not None:  # прибрати жовте виділення плейсхолдера
            for tag in ("w:highlight", "w:shd"):
                for el in rpr.findall(qn(tag)):
                    rpr.remove(el)
    d.save(out)
    print(f"Заповнено {len(runs)} плейсхолдерів -> {out}")


def check_claims(R: dict, D: dict) -> None:
    """Твердження, які вже написані в чернетці, мають збігатися з твоїми числами."""
    W = []
    if not R["python"].startswith("3.13"):
        W.append(f"у звіті «Python 3.13», а results.json виміряно на Python {R['python']}")
    if R.get("limit") != 50:
        W.append(f"у звіті «перші 50 документів», а --limit = {R.get('limit')}")
    if not D["slots"]["load_ms"] > D["plain"]["load_ms"]:
        W.append("у розділі 6 сказано, що slots-dataclass у pickle відновлюється повільніше "
                 "за звичайний, а за твоїми числами це не так — виправ це речення вручну")
    if not D["fm"]["binary"]["load_ms"] < D["fm"]["pickle"]["load_ms"]:
        W.append("binary не швидший за pickle при load — перевір текст про mmap")
    for w in W:
        print("УВАГА:", w, file=sys.stderr)


# ----------------------------- README ----------------------------------------
def readme(R: dict, D: dict) -> str:
    m, fm, ms, pf, pt, n = D["m"], D["fm"], D["ms"], D["pos_f"], D["pos_t"], D["n"]
    bpp = D["bpp"]
    L = ["# Лабораторна 2 — інвертований індекс", "",
         "Продовження `findex`: інвертований індекс над лінивим пайплайном Лаби 1, "
         "Boolean-пошук (merge / set), збереження в трьох форматах, вимірювання пам'яті.", "",
         "## Запуск", "", "```bash",
         "uv run python -m findex.index data/gutenberg --out index.fidx --format binary",
         'uv run python -m findex.search index.fidx "love war" --engine merge',
         "uv run python -m findex.bench_lab2 data/gutenberg --limit 50   # усі таблиці нижче",
         "```", "",
         "Запит: `a b` = AND; також `AND`/`OR`/`NOT` (верхній регістр), зліва направо. "
         "Формати: `--format pickle|json|binary`, позиції: `--positions`.", "",
         f"Вимірювання: Python {R['python']}, перші {R['n_docs']} документів корпусу Gutenberg "
         f"({i(R['n_terms'])} термінів, {i(n)} постінгів).", "",
         "## Пам'ять: три способи зберігання постінгів (tracemalloc)", "",
         "| Представлення | В пам'яті, МіБ | Пік build, МіБ | Байт/постінг | Файл pickle, МіБ | Load, мс |",
         "|---|---|---|---|---|---|"]
    for k in ("plain", "slots", "array"):
        r = m[k]
        L.append(f"| {r['name']} | {r['current_mib']:.1f} | {r['peak_mib']:.1f} | "
                 f"{bpp[k]:.0f} | {r['file_mib']:.2f} | {r['load_ms']:.0f} |")
    L += ["", "**Куди пішли байти.** `array('I')` — рівно 8 Б на постінг (2×u32) без об'єктів; "
          f"`slots=True` прибирає `__dict__` кожного екземпляра (≈{(m['plain']['current_mib'] - m['slots']['current_mib']) * MIB / n:.0f} Б "
          f"на постінг економії); решта — об'єкт ({R['sizes']['slots_obj']} Б), два int по "
          f"{R['sizes']['int']} Б і 8-байтовий вказівник у списку.", "",
          "## Формати збереження", "",
          "| Формат | Файл, МіБ | Save, мс | Load, мс |", "|---|---|---|---|"]
    for k in ("pickle", "json", "binary"):
        r = fm[k]
        L.append(f"| {k} | {r['file_mib']:.2f} | {r['save_ms']:.0f} | {r['load_ms']:.1f} |")
    L += ["", "> ⚠️ `pickle.load` виконує довільний код із файлу (`__reduce__`). "
          "Завантажуйте лише власні файли; для обміну — json або binary.", "",
          "## merge vs set (AND)", "",
          "| Пара | Терміни (df) | merge, мкс | set, мкс | Швидший |", "|---|---|---|---|---|"]
    for r in ms:
        L.append(f"| {r['label']} | {r['x']} ({r['dx']}), {r['y']} ({r['dy']}) | "
                 f"{r['merge_us']:.1f} | {r['set_us']:.1f} | {r['faster']} |")
    L += ["", "## Ціна `--positions`", "",
          "| positions | В пам'яті, МіБ | Пік, МіБ | Файл pickle, МіБ |", "|---|---|---|---|"]
    for r in (pf, pt):
        L.append(f"| {r['flag']} | {r['current_mib']:.1f} | {r['peak_mib']:.1f} | {r['file_mib']:.2f} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--results", default="results.json")
    ap.add_argument("--out", default="Лабораторна2_звіт.docx")
    ap.add_argument("--readme", default=None)
    a = ap.parse_args()
    with open(a.results, encoding="utf-8") as fh:
        R = json.load(fh)
    D = derive(R)
    check_claims(R, D)
    fill(a.template, a.out, placeholder_values(R, D))
    if a.readme:
        with open(a.readme, "w", encoding="utf-8") as fh:
            fh.write(readme(R, D))
        print("README ->", a.readme)


if __name__ == "__main__":
    main()
