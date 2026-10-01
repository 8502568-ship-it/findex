from dataclasses import dataclass, field
from typing import TypeAlias

DocId: TypeAlias = int


@dataclass(frozen=True, slots=True)
class Posting:
    doc_id: DocId
    term_frequency: int
    positions: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SearchResult:
    doc_id: DocId
    score: float
    title: str = ""
    snippet: str = ""