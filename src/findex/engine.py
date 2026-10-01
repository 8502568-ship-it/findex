"""Ранжований пошук: запит → дерево → множина документів → бали → топ-k → сніпети.

    python -m findex.engine index.pkl 'whale AND (sea OR ocean) NOT ship "white whale"' -k 5 -v
"""
from __future__ import annotations

import argparse
import functools
import logging

from findex.indexer import Index, open_index
from findex.query import QueryError, parse
from findex.ranking import BM25, Scorer, SearchResult, TfIdf, score_docs, top_k
from findex.snippets import make_snippet, read_text
from findex.util import timed

log = logging.getLogger("findex")
DEFAULT_SCORER = BM25()  # frozen dataclass: безпечний дефолт-аргумент


@timed
@functools.lru_cache(maxsize=256)
def match_ids(index: Index, query: str) -> tuple[int, ...]:
    """Шлях «запит → id документів» (кешується). Індекс хешується за ідентичністю,
    результат — tuple (незмінний, тож безпечно віддавати з кешу)."""
    return tuple(sorted(parse(query).evaluate(index)))


@timed
def search(index: Index, query: str, scorer: Scorer = DEFAULT_SCORER, k: int = 10,
           snippets: bool = False) -> list[SearchResult]:
    """Найкращі k документів за запитом, від найрелевантнішого."""
    ids = match_ids(index, query)
    terms = list(dict.fromkeys(parse(query).terms()))
    scores = score_docs(index, terms, ids, scorer)
    results = [SearchResult(d, s, index.title(d)) for d, s in top_k(scores, k)]
    if snippets:
        results = [SearchResult(r.doc_id, r.score, r.title,
                                make_snippet(read_text(index.path(r.doc_id)), terms))
                   for r in results]
    log.debug("match_ids cache: %s", match_ids.cache_info())
    return results


def clear_caches() -> None:
    match_ids.cache_clear()
    parse.cache_clear()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="findex.engine")
    ap.add_argument("index")
    ap.add_argument("query")
    ap.add_argument("--scorer", choices=["bm25", "tfidf"], default="bm25")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--no-snippets", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="лог @timed / кешу")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    scorer = BM25() if a.scorer == "bm25" else TfIdf()
    try:
        with open_index(a.index) as ix:
            print(ix)
            res = search(ix, a.query, scorer, a.k, snippets=not a.no_snippets)
    except QueryError as e:
        raise SystemExit(f"Помилка запиту: {e}") from e
    for r in res:
        print(r)
        if r.snippet:
            print(f"         {r.snippet}")
    if not res:
        print("нічого не знайдено")


if __name__ == "__main__":
    main()
