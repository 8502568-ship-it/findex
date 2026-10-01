"""M3 — збереження/завантаження індексу: pickle, json, binary (mmap)."""
from __future__ import annotations

import json
import mmap
import pickle
import struct
from array import array

from findex.models import DocMeta, MmapIndex, ObjectIndex, Posting
from findex.util import timed

MAGIC = b"FIDX1"


# ---------------------------------- pickle -----------------------------------
def save_pickle(idx, path) -> None:
    with open(path, "wb") as f:
        pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_pickle(path):
    # !!! БЕЗПЕКА: pickle.load виконує довільний код. Файл може містити
    # об'єкт, чий __reduce__ викликає, наприклад, os.system(...), і він
    # спрацює ПІД ЧАС load, ще до того як ти щось «використаєш».
    # Тому завантажуємо лише власноруч створені файли, ніколи — отримані
    # з мережі чи від інших людей.
    with open(path, "rb") as f:
        return pickle.load(f)


# ----------------------------------- json ------------------------------------
def save_json(idx, path) -> None:
    data = {
        "postings": {t: [[p, tf] for p, tf in zip(idx.doc_ids(t), idx.tfs(t))]
                     for t in idx.terms()},
        "doc_lengths": idx.doc_lengths,           # int-ключі стануть рядками
        "doc_meta": {str(d): [m.path, m.title] for d, m in idx.doc_meta.items()},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def load_json(path) -> ObjectIndex:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    idx = ObjectIndex({t: [Posting(d, tf) for d, tf in pl]
                       for t, pl in data["postings"].items()})
    idx.doc_lengths = {int(k): v for k, v in data["doc_lengths"].items()}
    idx.doc_meta = {int(k): DocMeta(int(k), p, t)
                    for k, (p, t) in data["doc_meta"].items()}
    return idx


# ------------------------- binary: JSON-заголовок + array ---------------------
# [MAGIC 5B][header_len u64][JSON header][blob]
# blob: для кожного терміна підряд doc_ids (n×u32) і tfs (n×u32), нативний порядок.
def save_binary(idx, path) -> None:
    toc: dict[str, list[int]] = {}
    off = 0
    chunks: list[bytes] = []
    for t in idx.terms():
        ids, tfs = array("I", idx.doc_ids(t)), array("I", idx.tfs(t))
        toc[t] = [off, len(ids)]
        chunks += [ids.tobytes(), tfs.tobytes()]
        off += 8 * len(ids)
    header = json.dumps({
        "itemsize": array("I").itemsize,
        "toc": toc,
        "doc_lengths": {str(k): v for k, v in idx.doc_lengths.items()},
        "doc_meta": {str(d): [m.path, m.title] for d, m in idx.doc_meta.items()},
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<Q", len(header)))
        f.write(header)
        f.writelines(chunks)


def load_binary(path) -> MmapIndex:
    fh = open(path, "rb")
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    if mm[:5] != MAGIC:
        raise ValueError("не бінарний індекс findex")
    (hlen,) = struct.unpack("<Q", mm[5:13])
    header = json.loads(mm[13:13 + hlen].decode("utf-8"))
    if header["itemsize"] != 4:
        raise ValueError("array('I') має розмір, відмінний від 4 байт")
    blob_start = 13 + hlen
    view = memoryview(mm)[blob_start:]
    toc = {t: (o, n) for t, (o, n) in header["toc"].items()}
    idx = MmapIndex(view, toc, mm, fh)
    idx.doc_lengths = {int(k): v for k, v in header["doc_lengths"].items()}
    idx.doc_meta = {int(k): DocMeta(int(k), p, t)
                    for k, (p, t) in header["doc_meta"].items()}
    return idx


# ------------------------------- загальний API --------------------------------
def save(idx, path, fmt: str = "pickle") -> None:
    {"pickle": save_pickle, "json": save_json, "binary": save_binary}[fmt](idx, path)


@timed
def load(path):
    """Формат визначається за першими байтами файлу."""
    with open(path, "rb") as f:
        head = f.read(5)
    if head == MAGIC:
        return load_binary(path)
    if head[:1] == b"{":
        return load_json(path)
    return load_pickle(path)
