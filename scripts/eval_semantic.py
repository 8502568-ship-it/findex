from __future__ import annotations

import json
from pathlib import Path

from findex.semantic import SemanticIndex, embed_query


def precision_at_5(results, relevant):
    relevant_lower = [x.lower() for x in relevant]
    hits = sum(
        any(term in result.title.lower() for term in relevant_lower)
        for result in results[:5]
    )
    return hits / 5


def main() -> None:
    eval_path = Path("eval_queries.json")
    data = json.loads(eval_path.read_text(encoding="utf-8"))
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
            "q": "a child wanders through an absurd realm where authority figures behave strangely",
            "relevant": ["Alice's Adventures", "Looking-Glass"],
        },
        {
            "q": "a respected physician conceals a disturbing alternate identity",
            "relevant": ["Jekyll"],
        },
        {
            "q": "an Earth traveler explores a hostile alien world and becomes involved with a local royal figure",
            "relevant": ["Mars"],
        },
    ]

    index = SemanticIndex.load(
        Path("semantic_embeddings.npy"),
        Path("semantic_embeddings.json"),
    )

    print("=== Semantic Precision@5 ===")
    scores = []
    for group, items in (("lab3", queries), ("paraphrase", paraphrases)):
        for item in items:
            results = index.search(embed_query(item["q"]), k=5)
            p5 = precision_at_5(results, item["relevant"])
            scores.append(p5)
            print(f"\\n[{group}] {item['q']}")
            print(f"P@5={p5:.2f} | relevant={item['relevant']}")
            for rank, result in enumerate(results, 1):
                print(f"  {rank}. {result.title} ({result.score:.4f})")

    print(f"\\nMean Precision@5 ({len(scores)} queries): {sum(scores) / len(scores):.3f}")


if __name__ == "__main__":
    main()
