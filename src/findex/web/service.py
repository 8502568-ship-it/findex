from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from findex.index import InvertedIndex
from findex.models import SearchResult


@dataclass(frozen=True, slots=True)
class WebDocument:
    doc_id: int
    title: str
    text: str


class WebSearch:
    def __init__(self, index: InvertedIndex, documents: dict[int, WebDocument]) -> None:
        self.index = index
        self.documents = documents

    @classmethod
    def load(cls, index_path: Path, docs_path: Path) -> WebSearch:
        index = InvertedIndex.load(index_path)
        documents: dict[int, WebDocument] = {}
        with docs_path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                doc_id = int(row["doc_id"])
                documents[doc_id] = WebDocument(
                    doc_id=doc_id,
                    title=str(
                        row.get("title")
                        or index.doc_titles.get(doc_id, f"Doc {doc_id}")
                    ),
                    text=str(row.get("text", "")),
                )
        return cls(index, documents)

    def _snippet(self, result: SearchResult, query: str) -> str:
        document = self.documents.get(result.doc_id)
        if document is None:
            return ""
        text = document.text.replace("\n", " ").strip()
        if not text:
            return ""
        terms = [re.escape(t) for t in query.split() if t]
        match = (
            re.search(r"(" + "|".join(terms) + r")", text, re.IGNORECASE)
            if terms
            else None
        )
        start = max(0, (match.start() - 90) if match else 0)
        end = min(len(text), start + 260)
        snippet = html.escape(text[start:end])
        if terms:
            safe_terms = [re.escape(html.escape(t)) for t in query.split() if t]
            if safe_terms:
                snippet = re.sub(
                    r"(" + "|".join(safe_terms) + r")",
                    r"<mark>\1</mark>",
                    snippet,
                    flags=re.IGNORECASE,
                )
        prefix = "…" if start else ""
        suffix = "…" if end < len(text) else ""
        return prefix + snippet + suffix

    def search(
        self,
        query: str,
        k: int,
        scorer: Literal["bm25", "tfidf"],
        page: int,
    ) -> tuple[list[dict[str, object]], int, int]:
        ranked = self.index.search(
            query=query,
            k=max(self.index.total_docs, 1),
            scorer_name=scorer,
        )
        total = len(ranked)
        start = (page - 1) * k
        page_results = ranked[start : start + k]
        results = [
            {
                "doc_id": r.doc_id,
                "title": self.documents.get(
                    r.doc_id, WebDocument(r.doc_id, r.title, "")
                ).title,
                "score": r.score,
                "snippet": self._snippet(r, query),
            }
            for r in page_results
        ]
        pages = math.ceil(total / k) if total else 0
        return results, total, pages

    def document(self, doc_id: int) -> WebDocument | None:
        return self.documents.get(doc_id)

    def stats(self) -> dict[str, float | int]:
        return {
            "documents": self.index.total_docs,
            "terms": len(self.index.postings),
            "average_document_length": self.index.avg_doc_len,
        }
