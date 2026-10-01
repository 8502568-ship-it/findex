from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class QueryNode:
    pass


@dataclass(frozen=True)
class TermNode(QueryNode):
    term: str


@dataclass(frozen=True)
class OpNode(QueryNode):
    op: Literal["AND", "OR"]
    left: QueryNode
    right: QueryNode


def parse_query(query: str) -> QueryNode:
    """Parse a simple Boolean query into an AST (supports AND, OR)."""
    parts = query.strip().split()
    if not parts:
        return TermNode("")

    if "OR" in parts:
        idx = parts.index("OR")
        left_q = " ".join(parts[:idx])
        right_q = " ".join(parts[idx + 1 :])
        return OpNode(op="OR", left=parse_query(left_q), right=parse_query(right_q))

    if "AND" in parts:
        idx = parts.index("AND")
        left_q = " ".join(parts[:idx])
        right_q = " ".join(parts[idx + 1 :])
        return OpNode(op="AND", left=parse_query(left_q), right=parse_query(right_q))

    return TermNode(term=parts[0].lower())