"""M3 — мова запитів: рекурсивний спуск → дерево вузлів.

    or_expr  := and_expr ('OR' and_expr)*
    and_expr := not_expr (['AND'] not_expr)*        # AND можна опускати
    not_expr := 'NOT' not_expr | atom
    atom     := WORD | "фраза" | '(' or_expr ')'

NOT зв'язує найсильніше, далі AND, найслабше — OR:
    a OR b c  ==  Or(a, And(b, c)).
Вузли перевантажують &, |, ~, тож запит можна скласти й без рядка:
    Term("python") & (Term("async") | Term("await")) & ~Term("java")
"""
from __future__ import annotations

import functools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from findex.tokenize import tokenize


class QueryError(ValueError):
    """Синтаксична помилка запиту або запит, який індекс не може виконати."""


# ------------------------------------ вузли ------------------------------------
class Node:
    """Базовий клас: оператори + контракт evaluate()/terms()."""

    def __and__(self, other: Node) -> And:
        return And(self, other)

    def __or__(self, other: Node) -> Or:
        return Or(self, other)

    def __invert__(self) -> Not:
        return Not(self)

    def evaluate(self, index) -> set[int]:  # pragma: no cover - інтерфейс
        raise NotImplementedError

    def terms(self) -> Iterator[str]:
        """Терміни, що впливають на ранжування (під NOT їх немає)."""
        return iter(())


@dataclass(frozen=True)
class Term(Node):
    text: str

    def evaluate(self, index) -> set[int]:
        return {p.doc_id for p in index.get(self.text, ())}

    def terms(self) -> Iterator[str]:
        yield self.text

    def __str__(self) -> str:
        return self.text


def _follow(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """Двовказівниковий merge за позиціями: позиції q з b, для яких q-1 є в a."""
    i = j = 0
    out: list[int] = []
    while i < len(a) and j < len(b):
        t = a[i] + 1
        if t == b[j]:
            out.append(b[j]); i += 1; j += 1
        elif t < b[j]:
            i += 1
        else:
            j += 1
    return out


@dataclass(frozen=True)
class Phrase(Node):
    words: tuple[str, ...]

    def evaluate(self, index) -> set[int]:
        if len(self.words) == 1:
            return Term(self.words[0]).evaluate(index)
        if not index.has_positions:
            raise QueryError('фразові запити потребують позицій: збудуйте індекс з --positions')
        maps = [{p.doc_id: p.positions for p in index.get(w, ())} for w in self.words]
        docs = set(maps[0])
        for m in maps[1:]:
            docs &= m.keys()
        hits = set()
        for d in docs:
            cur = maps[0][d]
            for m in maps[1:]:
                cur = _follow(cur, m[d])
                if not cur:
                    break
            if cur:
                hits.add(d)
        return hits

    def terms(self) -> Iterator[str]:
        yield from self.words

    def __str__(self) -> str:
        return '"' + " ".join(self.words) + '"'


@dataclass(frozen=True)
class And(Node):
    left: Node
    right: Node

    def evaluate(self, index) -> set[int]:
        if isinstance(self.right, Not):  # a AND NOT b  =  a \ b, без «всесвіту»
            return self.left.evaluate(index) - self.right.child.evaluate(index)
        return self.left.evaluate(index) & self.right.evaluate(index)

    def terms(self) -> Iterator[str]:
        yield from self.left.terms()
        yield from self.right.terms()

    def __str__(self) -> str:
        return f"({self.left} AND {self.right})"


@dataclass(frozen=True)
class Or(Node):
    left: Node
    right: Node

    def evaluate(self, index) -> set[int]:
        return self.left.evaluate(index) | self.right.evaluate(index)

    def terms(self) -> Iterator[str]:
        yield from self.left.terms()
        yield from self.right.terms()

    def __str__(self) -> str:
        return f"({self.left} OR {self.right})"


@dataclass(frozen=True)
class Not(Node):
    child: Node

    def evaluate(self, index) -> set[int]:
        return index.all_doc_ids() - self.child.evaluate(index)

    def __str__(self) -> str:
        return f"NOT {self.child}"


# ----------------------------------- лексер ------------------------------------
_KEYWORDS = {"AND", "OR", "NOT"}


def _lex(q: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1
        elif c in "()":
            out.append((c, c)); i += 1
        elif c == '"':
            j = q.find('"', i + 1)
            if j < 0:
                raise QueryError(f"не закрито лапки (позиція {i})")
            out.append(("PHRASE", q[i + 1 : j])); i = j + 1
        else:
            j = i
            while j < n and not q[j].isspace() and q[j] not in '()"':
                j += 1
            w = q[i:j]
            out.append((w, w) if w in _KEYWORDS else ("WORD", w)); i = j
    return out


# ----------------------------------- парсер ------------------------------------
class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.t, self.i = tokens, 0

    def peek(self) -> str | None:
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self) -> tuple[str, str]:
        tok = self.t[self.i]; self.i += 1
        return tok

    def or_expr(self) -> Node:
        node = self.and_expr()
        while self.peek() == "OR":
            self.take()
            node = Or(node, self.and_expr())
        return node

    def and_expr(self) -> Node:
        node = self.not_expr()
        while self.peek() is not None and self.peek() not in ("OR", ")"):
            if self.peek() == "AND":
                self.take()
            node = And(node, self.not_expr())
        return node

    def not_expr(self) -> Node:
        if self.peek() == "NOT":
            self.take()
            return Not(self.not_expr())
        return self.atom()

    def atom(self) -> Node:
        kind = self.peek()
        if kind is None:
            raise QueryError("запит обірвано: очікувався терм, фраза або '('")
        if kind == "(":
            self.take()
            node = self.or_expr()
            if self.peek() != ")":
                raise QueryError("немає закривної дужки ')'")
            self.take()
            return node
        if kind in ("WORD", "PHRASE"):
            _, text = self.take()
            words = tuple(tokenize(text))
            if not words:
                raise QueryError(f"'{text}' не містить жодного токена")
            if len(words) == 1:
                return Term(words[0])
            return Phrase(words)   # "event loop" і well-known (→ well known)
        raise QueryError(f"неочікуваний елемент '{kind}'")


@functools.lru_cache(maxsize=256)
def parse(query: str) -> Node:
    """Рядок → дерево. Вузли незмінні й хешовані, тому результат можна кешувати."""
    p = _Parser(_lex(query))
    if p.peek() is None:
        raise QueryError("порожній запит")
    node = p.or_expr()
    if p.peek() is not None:
        raise QueryError("зайва закривна дужка ')'")
    return node
