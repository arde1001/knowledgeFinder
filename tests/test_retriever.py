import re
import zlib

import numpy as np
import pytest

from kf import retriever as retriever_module
from kf.finder import Config, Finder, Result, Source
from kf.indexer import Index, build_index
from kf.labeler import build_filemap
from kf.perms import Policy
from kf.retriever import Retriever, RetrieverConfig

USERS = {"alice": {"roles": ["board"]}, "bob": {"roles": ["events"]}, "dave": {"roles": []}}
DRIVES = {
    "general": {"name": "General", "path": "general", "members": {"roles": ["*"]}, "contact_role": "Secretary"},
    "events": {"name": "Events", "path": "events", "members": {"roles": ["events"]}, "contact_role": "Events lead"},
    "board": {"name": "Board", "path": "board", "members": {"roles": ["board"]}, "contact_role": "Chair"},
}
FILLER = "\n".join(f"Paragraph {i} describes the weather and catering plans for the picnic in the park." for i in range(40))
FILES = {
    "events/gala.md": "The gala venue is Harbour Hall.\nCall Anna Virtanen on +358 40 555 1234 or mail anna.virtanen@example.org.\n"
                      "She lives at Koivukatu 12 B 7, 00100 Helsinki.",
    "events/long.md": FILLER + "\nThe secret booking code is ZX-9911-Q.",
    "board/budget.md": "The board approved the hackathon budget of 9000 euros.",
    "general/faq.md": "Membership is open to all students.",
}


def fake_embed(texts):
    out = np.zeros((len(texts), 512))
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z]+", t.lower()):
            out[i, zlib.crc32(w.encode()) % 512] += 1
    return out


class Counter:
    calls = 0

    def __call__(self, texts):
        Counter.calls += 1
        return fake_embed(texts)


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "drive"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return tmp_path, root


def make(env, shares=(), labelled_with=None, config=None):
    tmp, root = env
    meta = {p: {"created": "2025-01-01"} for p in FILES}
    labelling = labelled_with or Policy(USERS, DRIVES, list(shares))
    fm, _ = build_filemap(root, meta, labelling, lambda p, t: f"About {p}", lambda f, lines: f"Folder {f}")
    build_index(root, fm, labelling, tmp / "index", fake_embed, context=False)
    index = Index.load(tmp / "index", embed_query=lambda t: fake_embed([t])[0])
    finder = Finder(Policy(USERS, DRIVES, list(shares)), fm, index, root, Config(min_score=0.1))
    Counter.calls = 0
    return finder, Retriever(finder, config, embed_documents=Counter())


def source(path, drive="events"):
    return Source(path, drive, drive.title(), "2025-01-01", "d", 0.9, 0)


def test_passages_are_pii_stripped_and_carry_source_info(env):
    finder, r = make(env)
    q = "gala venue Harbour Hall"
    passages = r.retrieve("bob", q, finder.find("bob", q))
    assert [p.path for p in passages] == ["events/gala.md"]
    p = passages[0]
    assert "Harbour Hall" in p.text and "[phone]" in p.text and "[email]" in p.text and "[address]" in p.text
    assert not any(x in p.text for x in ("555", "anna.virtanen", "Koivukatu", "00100"))
    assert (p.drive, p.drive_name, p.created) == ("events", "Events", "2025-01-01") and 0 < p.score <= 1.0001


def test_unreadable_source_in_a_handmade_result_is_dropped(env):
    finder, r = make(env)
    passages = r.retrieve("bob", "budget", Result([source("board/budget.md", "board"), source("general/faq.md", "general")]))
    assert [p.path for p in passages] == ["general/faq.md"]
    assert r.dropped == [("board/budget.md", "not readable")]


def test_file_whose_permissions_changed_since_labelling_is_dropped(env):
    shares = [{"path": "events/gala.md", "users": ["dave"]}]
    finder, r = make(env, shares, labelled_with=Policy(USERS, DRIVES, []))
    assert r.retrieve("bob", "gala", Result([source("events/gala.md")])) == []
    assert r.dropped == [("events/gala.md", "not findable")]


def test_missing_file_is_dropped(env):
    finder, r = make(env)
    (env[1] / "events/gala.md").unlink()
    assert r.retrieve("bob", "gala", Result([source("events/gala.md")])) == []
    assert r.dropped[0][1] == "missing or outside the corpus"


def test_symlink_pointing_outside_the_corpus_is_dropped(env):
    tmp, root = env
    secret = tmp / "secret.md"
    secret.write_text("outside the corpus", encoding="utf-8")
    try:
        (root / "events/link.md").symlink_to(secret)
    except OSError:  # Windows without administrator rights or Developer Mode
        pytest.skip("symlinks are not allowed here")
    FILES["events/link.md"] = "outside the corpus"
    try:
        finder, r = make(env)
        assert r.retrieve("bob", "outside corpus", Result([source("events/link.md")])) == []
        assert r.dropped[0][1] == "missing or outside the corpus"
    finally:
        del FILES["events/link.md"]


def test_best_selection_finds_the_fact_deep_in_a_long_file(env):
    q = "secret booking code"
    finder, best = make(env, config=RetrieverConfig(per_source=1, select="best"))
    _, head = make(env, config=RetrieverConfig(per_source=1, select="head"))
    res = Result([source("events/long.md")])
    assert "ZX-9911-Q" in best.retrieve("bob", q, res)[0].text
    assert "ZX-9911-Q" not in head.retrieve("bob", q, res)[0].text


def test_passages_of_one_source_come_in_document_order(env):
    finder, r = make(env, config=RetrieverConfig(per_source=2))
    passages = r.retrieve("bob", "secret booking code", Result([source("events/long.md")]))
    text = (env[1] / "events/long.md").read_text(encoding="utf-8")
    positions = [text.index(p.text.split("\n")[0]) for p in passages]
    assert len(passages) == 2 and positions == sorted(positions)


def test_unchanged_file_reuses_stored_vectors_but_edited_file_is_reembedded(env):
    finder, r = make(env)
    q = "secret booking code"
    r.retrieve("bob", q, Result([source("events/long.md")]))
    assert Counter.calls == 0
    path = env[1] / "events/long.md"
    path.write_text(path.read_text(encoding="utf-8").replace("ZX-9911-Q", "NEW-4242-Z"), encoding="utf-8")
    passages = r.retrieve("bob", q, Result([source("events/long.md")]))
    assert Counter.calls == 1
    text = " ".join(p.text for p in passages)
    assert "NEW-4242-Z" in text and "ZX-9911-Q" not in text  # answers follow the current content


def test_total_text_stays_within_budget(env):
    finder, r = make(env, config=RetrieverConfig(per_source=2, max_chars=1200))
    passages = r.retrieve("bob", "picnic park catering gala", Result([source("events/long.md"), source("events/gala.md")]))
    assert passages and sum(len(p.text) for p in passages) <= 1200


def test_personal_data_left_after_stripping_drops_the_passage(env, monkeypatch):
    finder, r = make(env)
    monkeypatch.setattr(retriever_module, "strip", lambda text: text)  # simulate a stripper gap
    assert r.retrieve("bob", "gala", Result([source("events/gala.md")])) == []
    assert r.dropped == [("events/gala.md", "personal data left after stripping")]


def test_unchanged_file_is_extracted_once_edited_file_again(env, monkeypatch):
    finder, r = make(env)
    calls = []
    real = retriever_module.extract_text
    monkeypatch.setattr(retriever_module, "extract_text", lambda f: calls.append(f) or real(f))
    for _ in range(3):
        r.retrieve("bob", "gala", Result([source("events/gala.md")]))
    assert len(calls) == 1
    path = env[1] / "events/gala.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nThe gala moved to Pier Hall.", encoding="utf-8")
    assert "Pier Hall" in " ".join(p.text for p in r.retrieve("bob", "gala Pier Hall", Result([source("events/gala.md")])))
    assert len(calls) == 2
