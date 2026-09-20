"""Streaming tokenizer.

Policy (documented on purpose -- see README):
  * Unicode: NFC-normalize, then casefold (not lower()).
  * A token is a run of letters/digits: [^\\W_]+  (\\w is Unicode-aware; "_" is excluded).
  * Apostrophes INSIDE a word are kept:  don't, п'ять. The variants U+2019 (’),
    U+02BC (ʼ) and U+2032 (′) are mapped to ASCII "'" so п’ять == п'ять.
  * Hyphens SPLIT words: well-known -> well, known.
  * Digits are kept: 2024 and abc123 are tokens; 3.14 -> 3, 14.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2032": "'"})
TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def tokenize(text: str) -> Iterator[str]:
    text = unicodedata.normalize("NFC", text).casefold().translate(_APOSTROPHES)
    for match in TOKEN_RE.finditer(text):  # finditer, not findall: lazy
        yield match.group()
