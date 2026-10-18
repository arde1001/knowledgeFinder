import numpy as np
import pytest

from kf.indexer import Index
from kf.lexical import Bm25, tokenize

DOCS = [
    "spring gala plan venue booking reference VB-4821-K for the harbour hall",
    "spring gala budget euros catering sound system",
    "culture night plan cultural performances food stalls",
    "open mic night schedule and sign up for volunteers",
]


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("What is the Booking-Reference for VB-4821-K?") == ["booking", "reference", "vb", "4821", "k"]


def test_scores_are_zero_without_a_match_and_below_one():
    s = Bm25(DOCS).scores("harbour hall booking")
    assert s[0] > 0 and (s[1:] == 0).all() and s.max() < 1
    assert not Bm25(DOCS).scores("zebra").any()


def test_exact_code_ranks_its_document_first():
    assert int(np.argmax(Bm25(DOCS).scores("VB-4821-K"))) == 0


def test_term_missing_from_the_corpus_lowers_the_score():
    b = Bm25(DOCS)
    assert b.scores("lantern night").max() < b.scores("night").max()  # "lantern" occurs nowhere


def test_empty_inputs_are_safe():
    assert Bm25([]).scores("anything").shape == (0,)
    assert not Bm25(DOCS).scores("the of").any()


def test_index_bonus_changes_the_ranking():
    chunks = [{"path": p, "chunk": 0, "text": ""} for p in ("a", "b", "c")]
    vectors = np.array([[1, 0], [0.9, 0.436], [0, 1]], dtype=np.float32)
    idx = Index(vectors, chunks, {"model": ""}, embed_query=lambda t: [1, 0])
    q = idx.embed_query("x")
    assert [p for p, _, _ in idx.rank_files(q, k=3)] == ["a", "b", "c"]
    assert [p for p, _, _ in idx.rank_files(q, k=3, bonus=np.array([0, 0.5, 0]))] == ["b", "a", "c"]
    assert idx.rank_files(q, k=1, allowed={"c"}, bonus=np.array([0, 0, 0.25])) == [("c", pytest.approx(0.25), 0)]
