import logging
import math
from collections.abc import Mapping

import pytest

from findex.engine import clear_caches, match_ids, search
from findex.index import build_index
from findex.indexer import Index, open_index
from findex.pipeline import RawDoc
from findex.query import And, Not, Or, Phrase, QueryError, Term, parse
from findex.ranking import BM25, Scorer, SearchResult, TfIdf, top_k
from findex.snippets import make_snippet
from findex.store import save
from findex.util import timed

DOCS = [
    RawDoc("a", "A", "the event loop runs python async tasks"),
    RawDoc("b", "B", "python and java are languages the loop"),
    RawDoc("c", "C", "the the the the the the the the rare"),
    RawDoc("d", "D", "event then loop then python await"),
]


@pytest.fixture()
def ix():
    return Index(build_index(DOCS, "slots", positions=True))


# ---------------------------------- M1: Index ----------------------------------
def test_dunders(ix):
    assert isinstance(ix, Mapping)
    assert len(ix) == len(list(ix)) == len(ix.keys())
    assert "python" in ix and "cobol" not in ix
    assert [p.doc_id for p in ix["python"]] == [0, 1, 3]
    with pytest.raises(KeyError):
        ix["cobol"]
    assert ix.get("cobol") is None
    assert repr(ix) == f"Index(terms={len(ix)}, docs=4)"
    assert ix.num_docs == 4 and ix.df("python") == 3 and ix.df("cobol") == 0


def test_avg_doc_length_is_cached(ix):
    assert ix.avg_doc_length == sum(ix.doc_length(d) for d in range(4)) / 4
    assert "avg_doc_length" in vars(ix)        # cached_property лежить у __dict__


@pytest.mark.parametrize("fmt,variant", [("pickle", "slots"), ("json", "slots"),
                                         ("binary", "array")])
def test_open_index_all_formats(tmp_path, fmt, variant):
    p = tmp_path / "ix"
    save(build_index(DOCS, variant), p, fmt)
    with open_index(p) as ix:
        assert len(ix) > 0 and "python" in ix
        assert [x.doc_id for x in ix["python"]] == [0, 1, 3]


def test_open_index_releases_on_exception(tmp_path):
    p = tmp_path / "ix.bin"
    save(build_index(DOCS, "array"), p, "binary")
    with pytest.raises(RuntimeError), open_index(p) as ix:
        mm = ix.backend._mm
        raise RuntimeError("boom")
    assert mm.closed                           # ресурс звільнено попри виняток


# ------------------------------ M2: ранжування ---------------------------------
def test_scorers_satisfy_protocol():
    assert isinstance(TfIdf(), Scorer) and isinstance(BM25(), Scorer)


def test_rare_beats_common(ix):
    rare = ix["rare"][0]
    common = ix["the"][0]
    for s in (TfIdf(), BM25()):
        assert s.score("rare", rare, ix) > s.score("the", ix["the"][0], ix)
    assert common.tf >= 1


def test_bm25_saturation():
    many = build_index([RawDoc("x", "x", "w " * n + "filler " * 50) for n in (1, 2, 20, 21)]
                       + [RawDoc("y", "y", "other words here")], "slots")
    ix = Index(many)
    bm = BM25(b=0)
    sc = {n: bm.score("w", ix["w"][i], ix) for i, n in enumerate((1, 2, 20, 21))}
    assert sc[2] - sc[1] > 10 * (sc[21] - sc[20])      # 21-ше входження майже нічого не додає
    assert sc[21] < bm.idf("w", ix) * (bm.k1 + 1)      # стеля насичення


def test_bm25_short_beats_long():
    docs = [RawDoc("s", "short", "python rocks"),
            RawDoc("l", "long", "python " + "filler " * 500),
            RawDoc("o", "other", "something else entirely")]
    ix = Index(build_index(docs, "slots"))
    res = search(ix, "python", BM25())
    assert [r.title for r in res] == ["short", "long"]
    # TF-IDF довжини не враховує — бали однакові
    t = TfIdf()
    assert math.isclose(t.score("python", ix["python"][0], ix), t.score("python", ix["python"][1], ix))


def test_search_result_ordering():
    a, b, c = SearchResult(1, 0.5, "a"), SearchResult(2, 0.9, "b"), SearchResult(3, 0.5, "c")
    assert sorted([b, c, a], reverse=True) == [b, a, c]        # тай-брейк: менший doc_id вищий
    assert a == SearchResult(1, 0.5, "інший заголовок")         # eq за (score, doc_id)


def test_top_k_matches_sorted():
    scores = {i: (i * 7919) % 101 / 10 for i in range(200)}
    want = sorted(scores.items(), key=lambda kv: (kv[1], -kv[0]), reverse=True)[:10]
    assert top_k(scores, 10) == want


# ------------------------------ M3: мова запитів -------------------------------
def test_parser_trees():
    assert parse("a OR b c") == Or(Term("a"), And(Term("b"), Term("c")))
    assert parse("a b OR c") == Or(And(Term("a"), Term("b")), Term("c"))
    assert parse("a AND b AND c") == And(And(Term("a"), Term("b")), Term("c"))
    assert parse("NOT a b") == And(Not(Term("a")), Term("b"))
    assert parse('x "event loop"') == And(Term("x"), Phrase(("event", "loop")))
    assert parse('python AND (async OR await) NOT java "event loop"') == (
        Term("python") & (Term("async") | Term("await")) & ~Term("java") & Phrase(("event", "loop"))
    )
    assert parse("Python") == Term("python")                   # нормалізація як у токенайзері
    assert parse("well-known") == Phrase(("well", "known"))


@pytest.mark.parametrize("bad", ["", "a AND", "(a OR b", "a OR b)", '"a b', "OR a", '""'])
def test_parser_errors(bad):
    with pytest.raises(QueryError):
        parse(bad)


def test_evaluate(ix):
    ev = lambda q: sorted(parse(q).evaluate(ix))          
    assert ev("python async") == [0]
    assert ev("async OR await") == [0, 3]
    assert ev("python NOT java") == [0, 3]
    assert ev("NOT python") == [2]
    assert ev('"event loop"') == [0]                         # d: event ... loop — не поруч
    assert ev('"loop runs python"') == [0]
    assert ev("python AND (async OR await) NOT java") == [0, 3]
    assert ev("cobol") == []


def test_phrase_needs_positions():
    ix = Index(build_index(DOCS, "slots"))
    with pytest.raises(QueryError):
        parse('"event loop"').evaluate(ix)


# --------------------------- M4: декоратори, кеш, сніпети -----------------------
def test_timed_keeps_metadata_and_logs(caplog):
    @timed
    def f(x):
        """doc"""
        return x

    assert f.__name__ == "f" and f.__doc__ == "doc"
    with caplog.at_level(logging.DEBUG, logger="findex"):
        assert f(3) == 3
    assert "f took" in caplog.text


def test_cache_hit_visible_in_log(ix, caplog):
    clear_caches()
    with caplog.at_level(logging.DEBUG, logger="findex"):
        match_ids(ix, "python java")
        match_ids(ix, "python java")
    assert "[cache miss]" in caplog.text and "[cache hit]" in caplog.text
    assert match_ids.cache_info().hits == 1


def test_search_end_to_end(ix):
    res = search(ix, '"event loop" OR rare', k=5)
    assert next(r.title for r in res) in {"A", "C"}
    assert all(res[i] >= res[i + 1] for i in range(len(res) - 1))


def test_snippet_highlights_and_windows():
    text = "x " * 200 + "The Event Loop is here " + "y " * 200
    s = make_snippet(text, {"event", "loop"})
    assert "**Event**" in s and "**Loop**" in s and s.startswith("…") and s.endswith("…")
    assert len(s) < 220
    assert make_snippet("nothing here", {"zzz"}) == "nothing here"
