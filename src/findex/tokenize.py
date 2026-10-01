import re
from collections.abc import Iterable, Iterator

_WORD_PATTERN = re.compile(r"\b\w+\b", flags=re.UNICODE)


def tokenize(text: str) -> Iterator[str]:
    """Yield lowercased tokens from raw text using Unicode-aware matching."""
    for match in _WORD_PATTERN.finditer(text):
        token = match.group(0).lower()
        if token:
            yield token


def tokenize_all(texts: Iterable[str]) -> Iterator[str]:
    """Tokenize a stream of texts."""
    for text in texts:
        yield from tokenize(text)