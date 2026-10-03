from findex.index import InvertedIndex
from findex.parallel import build_index


def test_benchmark_search(benchmark) -> None:
    idx = InvertedIndex()
    for doc_id in range(20):
        idx.add_document(
            doc_id,
            f"Doc {doc_id}",
            "python asyncio search engine " * 20,
        )
    result = benchmark(idx.search, "python asyncio search", 10, "bm25")
    assert result


def test_benchmark_build_index(benchmark, tmp_path) -> None:
    corpus = []
    for i in range(8):
        path = tmp_path / f"{i}.txt"
        path.write_text("python asyncio search engine " * 50, encoding="utf-8")
        corpus.append(str(path))
    index, stats = benchmark(
        build_index,
        corpus,
        workers=1,
        executor="serial",
    )
    assert index.total_docs == 8
    assert stats.wall_seconds >= 0
