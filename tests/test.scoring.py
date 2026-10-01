from findex.scoring import BM25Scorer, TFIDFScorer


def test_bm25_zero_tf():
    scorer = BM25Scorer()
    assert scorer.score(doc_id=1, tf=0, doc_len=10, avg_doc_len=10.0, df=1, total_docs=10) == 0.0

def test_bm25_higher_tf_gives_higher_score():
    scorer = BM25Scorer()
    s1 = scorer.score(doc_id=1, tf=1, doc_len=10, avg_doc_len=10.0, df=2, total_docs=10)
    s2 = scorer.score(doc_id=1, tf=3, doc_len=10, avg_doc_len=10.0, df=2, total_docs=10)
    assert s2 > s1

def test_bm25_rarer_term_gives_higher_score():
    scorer = BM25Scorer()
    # df=1 (rarer) vs df=5 (common)
    s_rare = scorer.score(doc_id=1, tf=1, doc_len=10, avg_doc_len=10.0, df=1, total_docs=10)
    s_common = scorer.score(doc_id=1, tf=1, doc_len=10, avg_doc_len=10.0, df=5, total_docs=10)
    assert s_rare > s_common

def test_tfidf_monotonicity():
    scorer = TFIDFScorer()
    s1 = scorer.score(doc_id=1, tf=1, doc_len=10, avg_doc_len=10.0, df=2, total_docs=10)
    s2 = scorer.score(doc_id=1, tf=2, doc_len=10, avg_doc_len=10.0, df=2, total_docs=10)
    assert s2 > s1