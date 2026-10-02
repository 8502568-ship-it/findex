from findex.index import InvertedIndex
from findex.numpy_search import NumpyIndex


def make_index() -> InvertedIndex:
    idx = InvertedIndex()
    idx.add_document(0, "A", "python asyncio event loop")
    idx.add_document(1, "B", "python event loop event")
    idx.add_document(2, "C", "java database")
    return idx


def test_numpy_matches_python_order_and_scores() -> None:
    idx = make_index()
    np_idx = NumpyIndex.from_index(idx)
    for scorer in ("bm25", "tfidf"):
        expected = idx.search("python event", k=3, scorer_name=scorer)
        actual = np_idx.search("python event", k=3, scorer=scorer)
        assert [r.doc_id for r in actual] == [r.doc_id for r in expected]
        for left, right in zip(actual, expected):
            assert abs(left.score - right.score) < 1e-9


def test_numpy_storage_is_int32() -> None:
    idx = make_index()
    np_idx = NumpyIndex.from_index(idx)
    assert np_idx.doc_lengths.dtype.name == "int32"
    ids, tfs = np_idx.postings["python"]
    assert ids.dtype.name == "int32"
    assert tfs.dtype.name == "int32"
