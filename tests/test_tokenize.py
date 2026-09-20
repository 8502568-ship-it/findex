import inspect

from findex.tokenize import tokenize


def toks(text: str) -> list[str]:
    return list(tokenize(text))


def test_is_generator_function():
    assert inspect.isgeneratorfunction(tokenize)


def test_mixed_case():
    assert toks("Hello WORLD PyThOn") == ["hello", "world", "python"]


def test_cyrillic():
    assert toks("Привіт, СВІТЕ! Їжак") == ["привіт", "світе", "їжак"]


def test_combining_mark_is_normalized():
    # "cafe" + U+0301 (combining acute) must equal precomposed "café"
    assert toks("cafe\u0301") == toks("caf\u00e9") == ["caf\u00e9"]
    # same for Cyrillic: "и" + U+0306 -> "й"
    assert toks("\u0438\u0306") == ["\u0439"]


def test_punctuation_is_dropped():
    assert toks("one, two; (three)! ... four?") == ["one", "two", "three", "four"]


def test_empty_and_whitespace():
    assert toks("") == []
    assert toks("  \n\t ") == []


def test_apostrophes_kept_inside_words():
    assert toks("don't п'ять п\u2019ять") == ["don't", "п'ять", "п'ять"]


def test_hyphens_split_words():
    assert toks("well-known") == ["well", "known"]


def test_digits_and_underscore():
    assert toks("abc123 2024 3.14 snake_case") == ["abc123", "2024", "3", "14", "snake", "case"]


def test_casefold_beats_lower():
    assert toks("Straße") == toks("STRASSE") == ["strasse"]
