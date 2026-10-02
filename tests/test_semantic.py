import numpy as np

from findex.semantic import SemanticIndex


def test_semantic_returns_best_chunk_per_document() -> None:
    index = SemanticIndex(
        np.array([[1, 0], [0.8, 0.2], [0, 1]], dtype=np.float32),
        np.array([0, 0, 1], dtype=np.int32),
        ["alpha", "alpha better", "beta"],
        {0: "A", 1: "B"},
    )
    result = index.search(np.array([1, 0], dtype=np.float32), k=2)
    assert [hit.doc_id for hit in result] == [0, 1]
    assert result[0].text == "alpha"
