"""Експерименти Лаби 3 → results_lab3.json + README_lab3.md.

    python -m findex.lab3_eval data/gutenberg --limit 50
    python -m findex.lab3_eval --demo            # маленький корпус із pydoc_data (для перевірки)

Виконує: три sanity-перевірки ранжування, сліди @timed / cache hit, precision@5 для
TF-IDF vs BM25 (запити й мітки — eval_queries.json), демо-запит з дужками й фразою.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from itertools import islice
from pathlib import Path

from findex.engine import DEFAULT_SCORER, clear_caches, match_ids, search
from findex.index import build_index
from findex.indexer import Index, open_index
from findex.models import Posting
from findex.pipeline import iter_docs
from findex.ranking import BM25, TfIdf
from findex.store import save

DEMO_QUERIES = {
    "demo_query": '"context manager" AND (enter OR exit) NOT lambda',
    "queries": [
        {"q": "yield generator expression send", "relevant": ["^yield$"]},
        {"q": "context manager enter exit with statement", "relevant": ["^with$", "context-managers"]},
        {"q": "exception handler try except finally", "relevant": ["^try$", "^exceptions$", "^raise$"]},
        {"q": "import module package", "relevant": ["^import$"]},
        {"q": "string methods split join", "relevant": ["string-methods", "^strings$", "formatstrings"]},
        {"q": "dictionary key mapping", "relevant": ["^dict$", "typesmapping"]},
        {"q": "class definition inheritance metaclass", "relevant": ["^class$", "customization", "specialnames"]},
        {"q": "lambda anonymous function", "relevant": ["^lambda$", "^function$"]},
        {"q": "while loop break continue", "relevant": ["^while$", "^break$", "^continue$"]},
        {"q": "global nonlocal scope name binding", "relevant": ["^global$", "^nonlocal$", "naming", "execmodel"]},
    ],
}


def write_demo_corpus(root: Path) -> None:
    """Розділи мовного довідника Python (pydoc_data.topics) як «книги»."""
    from pydoc_data.topics import topics

    root.mkdir(parents=True, exist_ok=True)
    for key, text in topics.items():
        (root / f"{key}.txt").write_text(f"Title: {key}\n\n{text}", encoding="utf-8")


# ------------------------------ sanity-перевірки -------------------------------
def _alpha_terms(ix: Index) -> list[str]:
    return sorted(t for t in ix if t.isalpha() and len(t) >= 4)


def _closest(ix: Index, terms: list[str], frac: float) -> str:
    target = frac * ix.num_docs
    return min(terms, key=lambda t: (abs(ix.df(t) - target), t))


def sanity_checks(ix: Index) -> dict:
    scorers = {"tfidf": TfIdf(), "bm25": BM25()}
    terms = _alpha_terms(ix)
    avgdl = ix.avg_doc_length
    d_avg = min(ix.backend.doc_lengths, key=lambda d: (abs(ix.doc_length(d) - avgdl), d))

    # 1) рідкий термін вищий за частий (tf = 1, документ середньої довжини)
    rare = min((t for t in terms if ix.df(t) >= 1), key=lambda t: (ix.df(t), t))
    common = _closest(ix, terms, 0.6)
    p1 = Posting(d_avg, 1)
    c1 = {"rare": rare, "rare_df": ix.df(rare), "common": common, "common_df": ix.df(common),
          "doc_len": ix.doc_length(d_avg), "scores": {}}
    for name, s in scorers.items():
        c1["scores"][name] = {"rare": s.score(rare, p1, ix), "common": s.score(common, p1, ix)}
    c1["ok"] = all(v["rare"] > v["common"] for v in c1["scores"].values())

    # 2) 20-те повторення майже нічого не додає (документ середньої довжини)
    mid = _closest(ix, terms, 0.1)
    tfs = [1, 2, 5, 10, 20, 21, 50]
    c2 = {"term": mid, "df": ix.df(mid), "tfs": tfs, "scores": {}, "gain_1_2": {}, "gain_20_21": {},
          "ratio": {}, "bm25_ceiling": BM25().idf(mid, ix) * (BM25().k1 + 1)}
    for name, s in scorers.items():
        row = {tf: s.score(mid, Posting(d_avg, tf), ix) for tf in tfs}
        c2["scores"][name] = row
        c2["gain_1_2"][name] = row[2] - row[1]
        c2["gain_20_21"][name] = row[21] - row[20]
        c2["ratio"][name] = c2["gain_20_21"][name] / c2["gain_1_2"][name]
    c2["ok"] = c2["ratio"]["bm25"] < 0.05

    # 3) короткий документ з одним входженням вищий за дуже довгий
    lens = ix.backend.doc_lengths
    d_short, d_long = min(lens, key=lambda d: (lens[d], d)), max(lens, key=lambda d: (lens[d], -d))
    term3 = _closest(ix, terms, 0.3)
    c3 = {"term": term3, "short": {"title": ix.title(d_short), "len": lens[d_short]},
          "long": {"title": ix.title(d_long), "len": lens[d_long]}, "scores": {}}
    for name, s in scorers.items():
        c3["scores"][name] = {"short": s.score(term3, Posting(d_short, 1), ix),
                              "long": s.score(term3, Posting(d_long, 1), ix)}
    c3["ok"] = c3["scores"]["bm25"]["short"] > c3["scores"]["bm25"]["long"]
    return {"rare_vs_common": c1, "saturation": c2, "length_norm": c3}


# ----------------------------------- precision ---------------------------------
def precision_at_5(ix: Index, queries: list[dict]) -> dict:
    titles = {d: ix.title(d) for d in ix.backend.doc_meta}
    rows = []
    for item in queries:
        pats = [re.compile(p, re.IGNORECASE) for p in item["relevant"]]
        rel = {d for d, t in titles.items() if any(p.search(t) for p in pats)}
        row = {"q": item["q"], "relevant_in_corpus": len(rel), "scorers": {}}
        or_query = " OR ".join(item["q"].split())   # ранжуємо всю множину збігів, а не AND
        for name, s in (("tfidf", TfIdf()), ("bm25", BM25())):
            top = search(ix, or_query, s, k=5)
            hit = sum(r.doc_id in rel for r in top)
            row["scorers"][name] = {"hits": hit, "p5": hit / 5, "top5": [r.title for r in top]}
        rows.append(row)
    valid = [r for r in rows if r["relevant_in_corpus"] > 0]
    mean = {n: (sum(r["scorers"][n]["p5"] for r in valid) / len(valid) if valid else None)
            for n in ("tfidf", "bm25")}
    return {"rows": rows, "mean": mean, "n_valid": len(valid),
            "missing": [r["q"] for r in rows if r["relevant_in_corpus"] == 0]}


# ------------------------------------ головна ----------------------------------
class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.levelname} {record.getMessage()}")


def run(corpus: str, limit: int | None, index_path: str, queries_path: str | None,
        demo: bool) -> dict:
    handler = _Collect()
    lg = logging.getLogger("findex")
    lg.setLevel(logging.DEBUG)
    lg.addHandler(handler)
    qdata = DEMO_QUERIES if demo else json.loads(Path(queries_path).read_text(encoding="utf-8"))

    docs = iter_docs(corpus)
    t0 = time.perf_counter()
    raw = build_index(islice(docs, limit) if limit else docs, "slots", positions=True)
    build_s = time.perf_counter() - t0
    save(raw, index_path, "pickle")

    clear_caches()
    with open_index(index_path) as ix:
        R: dict = {
            "python": sys.version.split()[0], "demo": demo, "corpus": corpus, "limit": limit,
            "n_docs": ix.num_docs, "n_terms": len(ix), "avg_doc_length": ix.avg_doc_length,
            "n_tokens": sum(ix.backend.doc_lengths.values()), "repr": repr(ix),
            "build_s": build_s, "sanity": sanity_checks(ix),
        }
        # сліди кешу: той самий запит двічі
        handler.lines.clear()
        q = qdata["demo_query"]
        search(ix, q, DEFAULT_SCORER, k=5)   # miss
        search(ix, q, DEFAULT_SCORER, k=5)   # hit
        R["log"] = list(handler.lines)
        first = search(ix, q, DEFAULT_SCORER, k=5, snippets=True)
        R["cache_info"] = str(match_ids.cache_info())
        ms = {m.group(2): float(m.group(1)) for line in handler.lines
              if (m := re.search(r"match_ids took ([\d.]+) ms \[cache (hit|miss)\]", line))}
        R["demo_query"] = {"q": q, "miss_ms": ms["miss"], "hit_ms": ms["hit"],
                           "results": [{"score": r.score, "title": r.title, "snippet": r.snippet}
                                       for r in first]}
        R["p5"] = precision_at_5(ix, qdata["queries"])
    lg.removeHandler(handler)
    return R


def _sp(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _f(x: float, d: int = 3) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def render_readme(R: dict) -> str:
    s = R["sanity"]; a, b, c = s["rare_vs_common"], s["saturation"], s["length_norm"]
    ok = lambda v: "✅" if v else "❌"
    L = ["# Лабораторна 3 — ранжування та модель об'єктів", ""]
    if R["demo"]:
        L += ["> ⚠️ Числа нижче — на **демо-корпусі** (розділи довідника Python), не на Gutenberg.", ""]
    L += ["## Запуск", "", "```bash",
          "uv run python -m findex.index data/gutenberg --out index.pkl --positions",
          'uv run python -m findex.engine index.pkl \'whale AND (sea OR ocean) NOT ship "white whale"\' -k 5 -v',
          "uv run python -m findex.lab3_eval data/gutenberg --limit 50   # усі таблиці нижче",
          "uv run pytest && uv run ruff check .", "```", "",
          (f"Корпус: **{R['n_docs']}** документів, {_sp(R['n_terms'])} термінів, "
           f"{_sp(R['n_tokens'])} токенів (`{R['repr']}`); Python {R['python']}."), "",
          "## Три sanity-перевірки ранжування", "",
          (f"1. **Рідкий термін вищий за частий** {ok(a['ok'])} — `{a['rare']}` (df={a['rare_df']}) проти "
          f"`{a['common']}` (df={a['common_df']}), tf=1, документ довжиною {a['doc_len']}:"), "",
          "| Scorer | рідкий | частий |", "|---|---|---|"]
    for n in ("tfidf", "bm25"):
        L.append(f"| {n} | {_f(a['scores'][n]['rare'])} | {_f(a['scores'][n]['common'])} |")
    L += ["", (f"2. **20-те повторення майже нічого не додає** {ok(b['ok'])} — термін `{b['term']}` "
          f"(df={b['df']}), документ середньої довжини:"), "",
          "| tf | " + " | ".join(str(t) for t in b["tfs"]) + " |", "|---|" + "---|" * len(b["tfs"])]
    for n in ("tfidf", "bm25"):
        L.append(f"| {n} | " + " | ".join(_f(b["scores"][n][str(t)] if str(t) in b["scores"][n]
                                            else b["scores"][n][t]) for t in b["tfs"]) + " |")
    L += ["", (f"Приріст 20→21 відносно приросту 1→2: TF-IDF **{_f(b['ratio']['tfidf'] * 100, 1)}%**, "
          f"BM25 **{_f(b['ratio']['bm25'] * 100, 1)}%**; BM25 не перевищує стелі "
          f"(k1+1)·idf = {_f(b['bm25_ceiling'])}."), "",
          (f"3. **Короткий документ вищий за довгий** {ok(c['ok'])} — `{c['term']}`, tf=1 в обох: "
          f"«{c['short']['title']}» ({c['short']['len']} токенів) проти «{c['long']['title']}» "
          f"({c['long']['len']} токенів):"), "",
          "| Scorer | короткий | довгий |", "|---|---|---|"]
    for n in ("tfidf", "bm25"):
        L.append(f"| {n} | {_f(c['scores'][n]['short'])} | {_f(c['scores'][n]['long'])} |")
    L += ["", "TF-IDF довжину не враховує (бали рівні); BM25 штрафує довгий документ (b=0,75).", "",
          "## precision@5: TF-IDF vs BM25", "",
          ("Запити подано як `t1 OR t2 OR …`; «релевантні» — документи, назва яких збігається з "
          "регулярним виразом із `eval_queries.json`."), "",
          "| # | Запит | Релевантних у корпусі | TF-IDF P@5 | BM25 P@5 |", "|---|---|---|---|---|"]
    for i, r in enumerate(R["p5"]["rows"], 1):
        L.append(f"| {i} | {r['q']} | {r['relevant_in_corpus']} | {_f(r['scorers']['tfidf']['p5'], 1)} "
                 f"| {_f(r['scorers']['bm25']['p5'], 1)} |")
    m = R["p5"]["mean"]
    L += [f"| | **Середнє** ({R['p5']['n_valid']} запитів) | | **{_f(m['tfidf'], 2)}** | **{_f(m['bm25'], 2)}** |", ""]
    if R["p5"]["missing"]:
        L += ["Запити без релевантних документів у корпусі (виключено): " + "; ".join(R["p5"]["missing"]), ""]
    d = R["demo_query"]
    L += ["## Сліди @timed і кешу", "", "Запит виконано двічі підряд:", "", "```"] + R["log"] + ["```", "",
          (f"Крок «запит → id документів» (`match_ids`): miss {_f(d['miss_ms'], 3)} мс, hit {_f(d['hit_ms'], 3)} мс; "
          f"`{R['cache_info']}`."), "", "## Демо запиту з дужками й фразою", "", f"`{d['q']}`", ""]
    for r in d["results"]:
        L += [f"- **{_f(r['score'])}** — {r['title']}: {r['snippet']}"]
    return "\n".join(L) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="findex.lab3_eval")
    ap.add_argument("corpus", nargs="?", default="data/gutenberg")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--queries", default="eval_queries.json")
    ap.add_argument("--index", default="index_lab3.pkl")
    ap.add_argument("--out", default="results_lab3.json")
    ap.add_argument("--readme", default="README_lab3.md")
    a = ap.parse_args(argv)
    corpus = a.corpus
    if a.demo:
        corpus = "data/demo_topics"
        write_demo_corpus(Path(corpus))
    R = run(corpus, a.limit, a.index, a.queries, a.demo)
    Path(a.out).write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(a.readme).write_text(render_readme(R), encoding="utf-8")
    print(f"→ {a.out}, {a.readme}")
    print(R["sanity"]["rare_vs_common"]["ok"], R["sanity"]["saturation"]["ok"],
          R["sanity"]["length_norm"]["ok"], R["p5"]["mean"])


if __name__ == "__main__":
    main()
