from pathlib import Path

import pytest

from findex.index import InvertedIndex


@pytest.fixture(scope="session")
def small_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    corpus_dir = tmp_path_factory.mktemp("corpus")
    doc1 = corpus_dir / "doc1.txt"
    doc2 = corpus_dir / "doc2.txt"
    doc3 = corpus_dir / "doc3.txt"
    
    doc1.write_text("The quick brown fox jumps over the lazy dog.", encoding="utf-8")
    doc2.write_text("Search engines index documents and rank them using algorithms.", encoding="utf-8")
    doc3.write_text("Brown dogs and quick foxes are friendly animals.", encoding="utf-8")
    return corpus_dir

@pytest.fixture
def built_index(small_corpus: Path) -> InvertedIndex:
    idx = InvertedIndex()
    for doc_id, file in enumerate(sorted(small_corpus.glob("*.txt"))):
        idx.add_document(doc_id=doc_id, title=file.name, text=file.read_text(encoding="utf-8"))
    return idx