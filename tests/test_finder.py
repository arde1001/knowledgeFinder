import re
import zlib

import numpy as np
import pytest

from kf.finder import POOL, Config, Finder
from kf.indexer import Index, build_index
from kf.labeler import build_filemap
from kf.perms import Policy

USERS = {
    "alice": {"roles": ["board"]},
    "bob": {"roles": ["events"]},
    "erin": {"roles": ["events"]},
    "dave": {"roles": []},
}
DRIVES = {
    "general": {"name": "General", "path": "general", "members": {"roles": ["*"]}, "contact_role": "Secretary"},
    "events": {"name": "Events", "path": "events", "members": {"roles": ["events"]}, "contact_role": "Events lead"},
    "board": {"name": "Board", "path": "board", "members": {"roles": ["board"]}, "contact_role": "Chairperson"},
    "finance": {"name": "Finance", "path": "finance", "members": {"roles": ["finance"]}, "contact_role": "Treasurer"},
}
FILES = {
    "general/faq.md": "membership and joining faq",
    "events/gala.md": "gala venue booking reference harbour hall",
    "events/picnic.md": "picnic park sandwiches lemonade",
    "board/budget-a.md": "hackathon budget approved euros board",
    "board/budget-b.md": "hackathon budget revised board meeting euros",
    "board/budget-c.md": "hackathon budget minutes board approved",
    "finance/ledger-a.md": "hackathon ledger payments euros finance",
    "finance/ledger-b.md": "hackathon ledger invoices finance euros",
}
QUERY = "hackathon budget approved"


def fake_embed(texts):
    out = np.zeros((len(texts), 512))
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z]+", t.lower()):
            out[i, zlib.crc32(w.encode()) % 512] += 1
    return out


def make_finder(tmp_path, shares=(), config=None, labelled_with=None):
    root = tmp_path / "drive"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    meta = {p: {"created": "2025-01-01"} for p in FILES}
    labelling = labelled_with or Policy(USERS, DRIVES, list(shares))
    fm, _ = build_filemap(root, meta, labelling, lambda p, t: f"About {p}", lambda f, lines: f"Folder {f}")
    build_index(root, fm, labelling, tmp_path / "index", fake_embed, context=False)
    index = Index.load(tmp_path / "index", embed_query=lambda t: fake_embed([t])[0])
    return Finder(Policy(USERS, DRIVES, list(shares)), fm, index, root, config or Config(min_score=0.1))


def paths(result):
    return [s.path for s in result.sources]


def test_sources_are_only_readable_files(tmp_path):
    r = make_finder(tmp_path).find("bob", "gala venue booking")
    assert paths(r) == ["events/gala.md"]
    r = make_finder(tmp_path).find("alice", QUERY)
    assert all(p.startswith("board/") for p in paths(r))


def test_source_fields_come_from_the_filemap(tmp_path):
    s = make_finder(tmp_path).find("bob", "gala venue booking").sources[0]
    assert (s.drive, s.drive_name, s.created, s.description) == ("events", "Events", "2025-01-01", "About events/gala.md")
    assert 0 < s.score <= 1.0001


def test_dynamic_cut_drops_weak_results(tmp_path):
    f = make_finder(tmp_path)
    assert paths(f.decide(f.retrieve("alice", QUERY), Config(ratio=0.9, min_score=0.1))) == ["board/budget-a.md", "board/budget-c.md"]
    assert len(f.decide(f.retrieve("alice", QUERY), Config(ratio=0.5, min_score=0.1)).sources) == 3


def test_min_score_gives_empty_sources(tmp_path):
    f = make_finder(tmp_path)
    assert f.decide(f.retrieve("alice", QUERY), Config(min_score=0.99)).sources == []
    assert f.find("bob", "zebra quantum").sources == []


def test_denial_fires_when_enough_top_files_are_in_one_unreadable_drive(tmp_path):
    r = make_finder(tmp_path, config=Config(min_score=0.1, K=3, N=2)).find("bob", QUERY)
    assert r.sources == [] or all(not p.startswith("board/") for p in paths(r))
    assert r.denial is not None and (r.denial.drive, r.denial.contact_role) == ("board", "Chairperson")


def test_denial_exposes_only_drive_name_and_contact_role(tmp_path):
    r = make_finder(tmp_path, config=Config(min_score=0.1, K=3)).find("bob", QUERY)
    assert set(r.to_dict()["denial"]) == {"drive", "drive_name", "contact_role"}
    assert set(r.to_dict()) == {"sources", "denial"}


def test_no_denial_below_n_or_below_min_denial_score(tmp_path):
    f = make_finder(tmp_path)
    raw = f.retrieve("bob", QUERY)
    assert f.decide(raw, Config(K=3, N=4)).denial is None
    assert f.decide(raw, Config(K=3, N=2, min_denial_score=0.99)).denial is None


def test_only_the_strongest_drive_is_named(tmp_path):
    f = make_finder(tmp_path)  # K=5 holds board (3 files) and finance (2 files)
    assert {d for p, _, r in f.retrieve("bob", QUERY).overall[:5] if not r for d in [f.policy.drive_of(p)]} == {"board", "finance"}
    assert f.find("bob", QUERY).denial.drive == "board"


def test_partial_access_one_shared_file_still_leaves_two_unreadable(tmp_path):
    shares = [{"path": "board/budget-a.md", "users": ["erin"]}]
    f = make_finder(tmp_path, shares, Config(min_score=0.1, K=3, N=2))
    r = f.find("erin", QUERY)
    assert "board/budget-a.md" in paths(r)  # the shared file is a normal source
    assert r.denial is not None and r.denial.drive == "board"  # budget-b and budget-c remain unreadable


def test_partial_access_denial_stops_when_fewer_than_n_remain_unreadable(tmp_path):
    shares = [{"path": "board/budget-a.md", "users": ["erin"]}, {"path": "board/budget-c.md", "users": ["erin"]}]
    r = make_finder(tmp_path, shares, Config(min_score=0.1, K=3, N=2)).find("erin", QUERY)
    assert r.denial is None


def test_files_whose_permissions_changed_since_labelling_are_invisible(tmp_path):
    before = Policy(USERS, DRIVES, [])
    shares = [{"path": "events/gala.md", "users": ["dave"]}]  # permissions changed after labelling
    f = make_finder(tmp_path, shares, labelled_with=before)
    assert "events/gala.md" not in f.live
    assert paths(f.find("bob", "gala venue booking")) == []
    assert all(p != "events/gala.md" for p, _, _ in f.retrieve("bob", "gala venue booking").overall)


def test_unknown_user_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        make_finder(tmp_path).find("mallory", QUERY)


def test_user_without_roles_sees_only_general(tmp_path):
    r = make_finder(tmp_path).find("dave", "membership joining faq")
    assert paths(r) == ["general/faq.md"]


def test_config_validation(tmp_path):
    with pytest.raises(ValueError):
        Config(K=POOL + 1)
    p = tmp_path / "f.yaml"
    p.write_text("N: 3\nratio: 0.8\n", encoding="utf-8")
    assert Config.load(p).N == 3
    p.write_text("typo: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Config.load(p)


def test_repository_config_loads():
    from pathlib import Path

    cfg = Config.load(Path(__file__).parent.parent / "finder.yaml")
    assert cfg.N >= 2 and 0 < cfg.min_score < 1


def test_lexical_weight_adds_normalised_bm25_to_the_score(tmp_path):
    f = make_finder(tmp_path)
    base = f.retrieve("alice", QUERY, lex_weight=0).readable[0]
    boosted = f.retrieve("alice", QUERY, lex_weight=0.5).readable[0]
    chunk = next(i for i, c in enumerate(f.index.chunks) if (c["path"], c["chunk"]) == (base[0], base[2]))
    assert boosted[1] == pytest.approx(base[1] + 0.5 * f._lexical().scores(QUERY)[chunk], abs=1e-5)
    assert boosted[1] > base[1]


def test_negative_lexical_weight_rejected():
    with pytest.raises(ValueError):
        Config(lex_weight=-0.1)


from kf.finder import Raw


def test_best_mode_names_the_drive_of_an_unreadable_best_match(tmp_path):
    f = make_finder(tmp_path, config=Config(min_score=0.1, denial_mode="best"))
    d = f.find("bob", QUERY).denial
    assert (d.drive, d.contact_role) == ("board", "Chairperson")
    assert f.find("alice", QUERY).denial is None  # the best match is readable
    assert make_finder(tmp_path, config=Config(denial_mode="best")).find("bob", "gala venue booking").denial is None


def test_best_mode_one_unreadable_file_is_enough(tmp_path):
    f = make_finder(tmp_path, config=Config(min_score=0.1, denial_mode="best", margin=0.3))
    assert f.find("bob", "hackathon ledger payments euros").denial.drive == "finance"  # N=2 would not matter here


def test_best_mode_margin_needs_a_clear_lead_over_other_drives():
    f = Finder.__new__(Finder)  # decide() only needs the policy
    f.policy, f.live, f.config = Policy(USERS, DRIVES, []), {}, Config()
    raw = Raw(readable=[], overall=[("board/budget-a.md", 0.90, False), ("board/budget-b.md", 0.89, False), ("events/gala.md", 0.88, True)])
    assert f._best_denial(raw, Config(denial_mode="best", margin=0.05)) is None  # events/gala.md is too close
    assert f._best_denial(raw, Config(denial_mode="best", margin=0.01)).drive == "board"
    only_board = Raw(readable=[], overall=[("board/budget-a.md", 0.9, False), ("board/budget-b.md", 0.89, False)])
    assert f._best_denial(only_board, Config(denial_mode="best", margin=0.5)).drive == "board"  # nothing elsewhere competes
    assert f._best_denial(raw, Config(denial_mode="best", min_denial_score=0.95)) is None


def test_best_mode_never_exposes_more_than_cluster_mode(tmp_path):
    r = make_finder(tmp_path, config=Config(min_score=0.1, denial_mode="best")).find("bob", QUERY)
    assert set(r.to_dict()["denial"]) == {"drive", "drive_name", "contact_role"}


def test_denial_mode_validation():
    with pytest.raises(ValueError):
        Config(denial_mode="loud")
    with pytest.raises(ValueError):
        Config(margin=-1)
