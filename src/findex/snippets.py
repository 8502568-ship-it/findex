"""M4 — сніпети: вікно ±80 символів навколо найкращого входження з підсвіткою."""
from __future__ import annotations

import bisect
import re
import unicodedata
from collections import Counter
from collections.abc import Collection
from pathlib import Path

from findex.tokenize import _APOSTROPHES, TOKEN_RE

_WS = re.compile(r"\s+")


def read_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def make_snippet(text: str, terms: Collection[str], width: int = 80,
                 mark: tuple[str, str] = ("**", "**")) -> str:
    """Токени шукаємо так само, як токенайзер, але на NFC-тексті з оригінальним
    регістром (переклад апострофів 1:1 не зсуває індекси), тож вікно показує
    справжній текст, а не casefold-версію."""
    terms = set(terms)
    nfc = unicodedata.normalize("NFC", text)
    norm = nfc.translate(_APOSTROPHES)
    hits = [(m.start(), m.end(), m.group().casefold()) for m in TOKEN_RE.finditer(norm)
            if m.group().casefold() in terms]
    if not hits:
        return _WS.sub(" ", nfc[: 2 * width]).strip() + ("…" if len(nfc) > 2 * width else "")

    # ковзне вікно по входженнях: максимум різних термів, потім — входжень
    best, best_lr = (-1, -1), (0, 0)
    counts: Counter[str] = Counter()
    lo = 0
    for hi, (_, e, t) in enumerate(hits):
        counts[t] += 1
        while e - hits[lo][0] > 2 * width:
            counts[hits[lo][2]] -= 1
            if not counts[hits[lo][2]]:
                del counts[hits[lo][2]]
            lo += 1
        score = (len(counts), hi - lo + 1)
        if score > best:
            best, best_lr = score, (lo, hi)
    anchor = hits[(best_lr[0] + best_lr[1]) // 2]

    start, end = max(0, anchor[0] - width), min(len(nfc), anchor[1] + width)
    while start > 0 and norm[start - 1].isalnum():   # не різати слово навпіл
        start -= 1
    while end < len(nfc) and norm[end].isalnum():
        end += 1

    starts = [h[0] for h in hits]
    out, pos = [], start
    for s, e, _ in hits[bisect.bisect_left(starts, start): bisect.bisect_right(starts, end - 1)]:
        out += [nfc[pos:s], mark[0], nfc[s:e], mark[1]]
        pos = e
    out.append(nfc[pos:end])
    body = _WS.sub(" ", "".join(out)).strip()
    return ("…" if start > 0 else "") + body + ("…" if end < len(nfc) else "")
