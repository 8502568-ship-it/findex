import inspect
import json

import pytest

from findex.corpus import iter_documents


def test_is_generator_function():
    assert inspect.isgeneratorfunction(iter_documents)


def test_txt_tree_and_lazy(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("бета", encoding="utf-8")
    (tmp_path / "ignore.md").write_text("no", encoding="utf-8")
    gen = iter_documents(tmp_path)
    first = next(gen)  # returns after reading ONE document
    assert first.doc_id == 0
    rest = list(gen)
    assert {first.text, rest[0].text} == {"alpha", "бета"}
    assert len(rest) == 1


def test_bad_encoding_does_not_crash(tmp_path, caplog):
    (tmp_path / "bad.txt").write_bytes(b"ok \xff\xfe bytes")
    docs = list(iter_documents(tmp_path))
    assert len(docs) == 1
    assert "\ufffd" in docs[0].text
    assert "bad UTF-8" in caplog.text


def test_jsonl(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text(
        json.dumps({"text": "one"}) + "\nnot json\n" + json.dumps({"text": "two"}) + "\n",
        encoding="utf-8",
    )
    assert [d.text for d in iter_documents(p)] == ["one", "two"]


def test_missing_root_raises_on_consumption(tmp_path):
    gen = iter_documents(tmp_path / "nope")  # no error yet: lazy
    with pytest.raises(FileNotFoundError):
        next(gen)
