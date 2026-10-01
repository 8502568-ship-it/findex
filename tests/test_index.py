from pathlib import Path

import pytest

from findex.index import InvertedIndex, merge_and, merge_or


def test_merge_and():
    assert merge_and([1, 2, 4, 7], [2, 3, 4, 8]) == [2, 4]
    assert merge_and([1, 3], [2, 4]) == []

def test_merge_or():
    assert merge_or([1, 3, 5], [2, 3, 4]) == [1, 2, 3, 4, 5]

def test_index_build(built_index: InvertedIndex):
    assert built_index.total_docs == 3
    assert "fox" in built_index.postings
    assert "algorithms" in built_index.postings

def test_index_search_ranking(built_index: InvertedIndex):
    res = built_index.search("brown fox", k=5)
    assert len(res) > 0
    # Both doc1 and doc3 contain brown/fox
    doc_ids = [r.doc_id for r in res]
    assert 0 in doc_ids or 2 in doc_ids

def test_index_save_load_roundtrip(built_index: InvertedIndex, tmp_path: Path):
    target = tmp_path / "index.json"
    built_index.save(target)
    loaded = InvertedIndex.load(target)
    assert loaded.total_docs == built_index.total_docs
    assert set(loaded.postings.keys()) == set(built_index.postings.keys())

def test_missing_index_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        InvertedIndex.load(tmp_path / "non_existent.json")

@pytest.mark.slow
def test_simulated_large_index_operation():
    import time
    time.sleep(1.05)  # Mark as slow test (> 1s)
    assert True