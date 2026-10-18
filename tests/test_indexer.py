import re
import zlib

import numpy as np
import pytest

from kf.indexer import Index, build_index, chunk_text, embedding_input
from kf.labeler import build_filemap
from kf.perms import Policy

USERS = {"bob": {"roles": ["events"]}}
DRIVES = {
    "events": {"name": "Events", "path": "events", "members": {"roles": ["events"]}, "contact_role": "Events lead"},
    "board": {"name": "Board", "path": "board", "members": {"roles": ["board"]}, "contact_role": "Chair"},
}
FILES = {
    "events/gala.md": "The gala venue is the Harbour Hall. Contact anna@example.org for keys.",
    "events/picnic.md": "The picnic needs sandwiches and lemonade for the park.",
    "board/budget.md": "The board approved the new hackathon budget of 9000 euros.",
}


def fake_embed(texts):
    """Deterministic bag-of-words vectors: texts sharing words are close."""
    out = np.zeros((len(texts), 64))
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z]+", t.lower()):
            out[i, zlib.crc32(w.encode()) % 64] += 1
    return out


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "drive"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    meta = {p: {"created": "2025-01-01"} for p in FILES}
    policy = Policy(USERS, DRIVES, [])
    fm, _ = build_filemap(root, meta, policy, lambda p, t: f"About {p}", lambda f, lines: f"Folder {f}")
    return root, fm, policy, tmp_path / "index"


def test_chunk_text_short_text_is_one_chunk():
    assert chunk_text("One line.\n\nAnother line.") == ["One line.\nAnother line."]
    assert chunk_text("") == [] and chunk_text("\n \n") == []


def test_chunk_text_respects_limit_and_loses_nothing():
    text = "\n".join(f"Sentence number {i} is here. " * 12 for i in range(30))
    chunks = chunk_text(text, limit=300)
    assert all(0 < len(c) <= 300 for c in chunks) and len(chunks) > 5
    words = lambda s: re.findall(r"\w+", s)
    assert words(" ".join(chunks)) == words(text)
    assert chunk_text("x" * 700, limit=300) == ["x" * 300, "x" * 300, "x" * 100]


def test_only_live_files_are_indexed(corpus):
    root, fm, policy, out = corpus
    (root / "events/unlabelled.md").write_text("never labelled", encoding="utf-8")
    changed = Policy(USERS, DRIVES, [{"path": "board/budget.md", "users": ["bob"]}])  # permissions changed since labelling
    meta = build_index(root, fm, changed, out, fake_embed)
    paths = {c["path"] for c in Index.load(out).chunks}
    assert paths == {"events/gala.md", "events/picnic.md"} and meta["files"] == 2


def test_pii_never_reaches_the_embedder_or_the_index(corpus):
    root, fm, policy, out = corpus
    seen = []
    build_index(root, fm, policy, out, lambda texts: seen.extend(texts) or fake_embed(texts))
    assert not any("anna@example.org" in t for t in seen)
    assert any("[email]" in c["text"] for c in Index.load(out).chunks)
    assert "anna@example.org" not in (out / "chunks.json").read_text(encoding="utf-8")


def test_context_prefixes_the_label_only_when_enabled(corpus):
    root, fm, policy, out = corpus
    on, off = [], []
    build_index(root, fm, policy, out, lambda t: on.extend(t) or fake_embed(t), context=True)
    build_index(root, fm, policy, out, lambda t: off.extend(t) or fake_embed(t), context=False)
    assert any(t.startswith("gala.md: About events/gala.md\n") for t in on)
    assert not any("About events" in t for t in off)
    assert embedding_input("a/b.md", "desc", "text", True) == "b.md: desc\ntext"


def test_rank_files_best_chunk_per_file_and_allowed_filter(corpus):
    root, fm, policy, out = corpus
    build_index(root, fm, policy, out, fake_embed)
    index = Index.load(out, embed_query=lambda t: fake_embed([t])[0])
    q = index.embed_query("hackathon budget")
    ranked = index.rank_files(q, k=3)
    assert ranked[0][0] == "board/budget.md" and len({p for p, _, _ in ranked}) == len(ranked) == 3
    restricted = index.rank_files(q, k=3, allowed={"events/gala.md", "events/picnic.md"})
    assert {p for p, _, _ in restricted} == {"events/gala.md", "events/picnic.md"}
    assert index.rank_files(q, k=3, allowed=set()) == []


def test_vectors_are_unit_length(corpus):
    root, fm, policy, out = corpus
    build_index(root, fm, policy, out, fake_embed)
    assert np.allclose(np.linalg.norm(Index.load(out).vectors, axis=1), 1.0)
