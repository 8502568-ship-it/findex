import pytest
from findex.tokenizer import tokenize


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello World!", ["hello", "world"]),
        ("Python 3.12 is great.", ["python", "3", "12", "is", "great"]),
        ("Київ — столиця України", ["київ", "столиця", "україни"]),
        ("", []),
        ("   ", []),
        ("Special @#$% symbols!", ["special", "symbols"]),
        ("Case-insensitive CaSe", ["case", "insensitive", "case"]),
        ("Tabs\tand\nnewlines", ["tabs", "and", "newlines"]),
    ],
)
def test_tokenize_various_inputs(text: str, expected: list[str]):
    assert list(tokenize(text)) == expected