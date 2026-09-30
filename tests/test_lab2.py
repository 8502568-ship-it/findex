import dataclasses
import os
import random
import tempfile

import pytest

from findex.index import build_index
from findex.models import DocMeta, Posting
from findex.pipeline import RawDoc
from findex.search import ENGINES, evaluate
from findex.store import load, save

DOCS = [RawDoc("a", "a", "python dict hash"), RawDoc("b", "b", "python set"),
        RawDoc("c", "c", "dict set pickle"), RawDoc("d", "d", "python pickle dict dict")]


def test_hashable_and_slots():
    p, m = Posting(1, 2), DocMeta(1, "p", "t")
    assert len({p, Posting(1, 2)}) == 1 and hash(m)
    assert not hasattr(p, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.tf = 5


@pytest.mark.parametrize("variant", ["plain", "slots", "array"])
def test_sorted_and_tf(variant):
    idx = build_index(DOCS, variant)
    assert list(idx.doc_ids("dict")) == [0, 2, 3]
    assert list(idx.tfs("dict")) == [1, 1, 2]
    assert idx.doc_lengths[3] == 4


def test_positions():
    idx = build_index(DOCS, "slots", positions=True)
    assert idx.postings["dict"][2].positions == (2, 3)


@pytest.mark.parametrize("engine", ["merge", "set"])
def test_queries(engine):
    idx = build_index(DOCS, "slots")
    assert evaluate(idx, "python dict", engine) == [0, 3]
    assert evaluate(idx, "python OR set", engine) == [0, 1, 2, 3]
    assert evaluate(idx, "dict NOT pickle", engine) == [0]
    assert evaluate(idx, "NOT python", engine) == [2]
    assert evaluate(idx, "nonexistent", engine) == []


def test_merge_equals_set_random():
    r = random.Random(1)
    for _ in range(200):
        a = sorted(r.sample(range(60), r.randint(0, 30)))
        b = sorted(r.sample(range(60), r.randint(0, 30)))
        for i in range(3):
            assert ENGINES["merge"][i](a, b) == ENGINES["set"][i](a, b)


@pytest.mark.parametrize("fmt,variant", [("pickle", "slots"), ("json", "slots"),
                                         ("binary", "array"), ("binary", "slots")])
def test_roundtrip(fmt, variant):
    idx = build_index(DOCS, variant)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "i")
        save(idx, p, fmt)
        r = load(p)
        for t in idx.terms():
            assert list(r.doc_ids(t)) == list(idx.doc_ids(t))
            assert list(r.tfs(t)) == list(idx.tfs(t))
        assert r.doc_lengths == idx.doc_lengths and r.doc_meta == idx.doc_meta
        assert evaluate(r, "python dict") == [0, 3]
        if hasattr(r, "close"):
            r.close()
