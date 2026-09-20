"""Lazy document stream: one document in memory at a time, never the whole corpus."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)


class Document(NamedTuple):
    doc_id: int
    path: Path
    text: str


def _read_text(path: Path) -> str | None:
    """Read one file as UTF-8; never crash on a bad file (log and go on)."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        log.warning("bad UTF-8 in %s, decoding with errors='replace'", path)
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None


def _iter_txt_tree(root: Path) -> Iterator[tuple[Path, str]]:
    for path in root.rglob("*.txt"):  # rglob is lazy too
        text = _read_text(path)
        if text is not None:
            yield path, text


def _iter_jsonl(path: Path) -> Iterator[tuple[Path, str]]:
    """One JSON object per line, document text in the "text" field."""
    with path.open(encoding="utf-8", errors="replace") as f:  # file = lazy line iterator
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                text = json.loads(line)["text"]
            except (json.JSONDecodeError, KeyError, TypeError):
                log.warning("skipping bad JSON record at %s:%d", path, lineno)
                continue
            if isinstance(text, str):
                yield path, text
            else:
                log.warning("non-string 'text' at %s:%d", path, lineno)


def iter_documents(root: Path) -> Iterator[Document]:
    """Yield documents one by one.

    `root` is either a directory tree of *.txt files or a single .jsonl file.
    This is a generator: calling it reads nothing; each next() reads one document.
    """
    root = Path(root)
    if not root.exists():
        # raised on the first next(), not at call time -- generators are lazy
        raise FileNotFoundError(root)
    source = _iter_jsonl(root) if root.is_file() else _iter_txt_tree(root)
    for doc_id, (path, text) in enumerate(source):
        yield Document(doc_id, path, text)
