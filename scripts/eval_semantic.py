from __future__ import annotations

import json
import re
from pathlib import Path

from findex.corpus import iter_documents
from findex.semantic import SemanticIndex, embed_query


def corpus_titles(corpus: Path) -> dict[int, str]:
    titles: dict[int, str] = {}
    for doc in iter_documents(corpus):
        match = re.search(r"(?im)^Title:\s*(.+?)\s*$", doc.text[:12000])
        titles[doc.doc_id] = match.group(1).strip() if match else doc.path.name
    return titles


def precision_at_5(results, relevant: list[str], titles: dict[int, str]) -> float:
    relevant_lower = [x.casefold() for x in relevant]
    hits = sum(
        any(
            term in titles.get(result.doc_id, result.title).casefold()
            for term in relevant_lower
        )
        for result in results[:5]
    )
    return hits / 5


def main() -> None:
    data = json.loads(Path("eval_queries.json").read_text(encoding="utf-8"))
    queries = data["queries"]
    paraphrases = [
        {
            "q": "a seafaring captain pursues an enormous animal across the ocean",
            "relevant": ["Moby"],
        },
        {
            "q": "a young scientist faces the consequences of creating living matter",
            "relevant": ["Frankenstein"],
        },
        {
            "q": (
                "a child wanders through an absurd realm where "
                "authority figures behave strangely"
            ),
            "relevant": ["Alice's Adventures", "Looking-Glass"],
        },
        {
            "q": "a respected physician conceals a disturbing alternate identity",
            "relevant": ["Jekyll"],
        },
        {
            "q": (
                "an Earth traveler explores a hostile alien world "
                "and becomes involved with a local royal figure"
            ),
            "relevant": ["Mars"],
        },
    ]

    index = SemanticIndex.load(
        Path("web/demo_embeddings.npy"),
        Path("web/demo_embeddings.json"),
    )
    titles = corpus_titles(Path("data/gutenberg"))

    print("=== Semantic Precision@5 ===")
    scores: list[float] = []
    for group, items in (("lab3", queries), ("paraphrase", paraphrases)):
        for item in items:
            results = index.search(embed_query(item["q"]), k=5)
            p5 = precision_at_5(results, item["relevant"], titles)
            scores.append(p5)
            print(f"\n[{group}] {item['q']}")
            print(f"P@5={p5:.2f} | relevant={item['relevant']}")
            for rank, result in enumerate(results, 1):
                display = titles.get(result.doc_id, result.title)
                print(f"  {rank}. {display} [{result.title}] ({result.score:.4f})")

    print(
        f"\nMean Precision@5 ({len(scores)} queries): "
        f"{sum(scores) / len(scores):.3f}"
    )


if __name__ == "__main__":
    main()
