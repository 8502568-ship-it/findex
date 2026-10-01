from findex.parser import OpNode, TermNode, parse_query


def test_parse_single_term():
    node = parse_query("search")
    assert isinstance(node, TermNode)
    assert node.term == "search"

def test_parse_and_query():
    node = parse_query("apple AND banana")
    assert isinstance(node, OpNode)
    assert node.op == "AND"
    assert node.left == TermNode("apple")
    assert node.right == TermNode("banana")

def test_parse_or_query():
    node = parse_query("cats OR dogs")
    assert isinstance(node, OpNode)
    assert node.op == "OR"
    assert node.left == TermNode("cats")
    assert node.right == TermNode("dogs")

def test_parse_empty():
    node = parse_query("")
    assert isinstance(node, TermNode)
    assert node.term == ""