from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from functools import lru_cache

import numpy as np


@dataclass(frozen=True, slots=True)
class SemanticHit:
    doc_id: int
    score: float
    title: str
    text: str


class SemanticIndex:
    """Normalized chunk embeddings stored in a NumPy matrix."""

    def __init__(
        self,
        embeddings: np.ndarray,
        doc_ids: np.ndarray,
        texts: list[str],
        titles: dict[int, str],
    ) -> None:
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        self.doc_ids = np.asarray(doc_ids, dtype=np.int32)
        self.texts = texts
        self.titles = titles

    @classmethod
    def load(cls, embeddings_path: Path, metadata_path: Path) -> "SemanticIndex":
        embeddings = np.load(embeddings_path, mmap_mode="r")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return cls(
            embeddings,
            np.asarray(metadata["doc_ids"], dtype=np.int32),
            metadata["texts"],
            {int(k): v for k, v in metadata["titles"].items()},
        )

    def search(self, query_vector: np.ndarray, k: int = 10) -> list[SemanticHit]:
        vector = np.asarray(query_vector, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0 or len(self.embeddings) == 0:
            return []
        vector = vector / norm
        scores = self.embeddings @ vector
        best_by_doc: dict[int, tuple[float, int]] = {}
        for row, score in enumerate(scores):
            doc_id = int(self.doc_ids[row])
            score_f = float(score)
            current = best_by_doc.get(doc_id)
            if current is None or score_f > current[0]:
                best_by_doc[doc_id] = (score_f, row)
        ranked = sorted(
            best_by_doc.items(), key=lambda item: (-item[1][0], item[0])
        )[:k]
        return [
            SemanticHit(
                doc_id=doc_id,
                score=score,
                title=self.titles.get(doc_id, f"Doc {doc_id}"),
                text=self.texts[row],
            )
            for doc_id, (score, row) in ranked
        ]


def _chunks(text: str, size: int = 12000, overlap: int = 1000) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    step = max(1, size - overlap)
    return [text[i : i + size] for i in range(0, len(text), step)]


def build_embeddings(
    documents: list[tuple[int, str, str]],
    output: Path,
    metadata_path: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Semantic search requires sentence-transformers; install the semantic extra."
        ) from exc

    texts: list[str] = []
    doc_ids: list[int] = []
    titles: dict[int, str] = {}
    for doc_id, title, text in documents:
        titles[doc_id] = title
        for chunk in _chunks(text):
            doc_ids.append(doc_id)
            texts.append(chunk[:800])
    if not texts:
        raise ValueError("No non-empty document chunks to embed.")

    model = SentenceTransformer(model_name)
    embedding_inputs = [
        f"{titles[doc_id]}\n{text}"
        for doc_id, text in zip(doc_ids, texts, strict=True)
    ]
    embeddings = model.encode(
        embedding_inputs,
        batch_size=128,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    np.save(output, np.asarray(embeddings, dtype=np.float32))
    metadata_path.write_text(
        json.dumps(
            {"doc_ids": doc_ids, "texts": texts, "titles": titles},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@lru_cache(maxsize=2)
def _model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Semantic search requires sentence-transformers; install the semantic extra."
        ) from exc
    return SentenceTransformer(model_name)


def embed_query(
    query: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> np.ndarray:
    model = _model(model_name)
    return np.asarray(
        model.encode([query], normalize_embeddings=True)[0],
        dtype=np.float32,
    )
