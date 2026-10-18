import pytest

from kf.corpus.generate import build, verify
from kf.corpus.spec import DRIVES, ENTITIES, ROLE_BOARD, ROLE_LEADER, ROLE_MEMBER, build_spec
from kf.perms import Policy


@pytest.fixture(scope="module")
def spec():
    return build_spec(1)


def test_deterministic():
    a, b = build_spec(1), build_spec(1)
    assert [f.path for f in a.files] == [f.path for f in b.files]
    assert a.shares == b.shares and a.users == b.users
    assert [x["question"] for f in a.files for x in f.facts] == [x["question"] for f in b.files for x in f.facts]


def test_shape(spec):
    assert len(spec.users) == 3 + 2 * (2 + 6)
    assert set(spec.drives) == set(DRIVES) and {d["name"] for d in spec.drives.values()} == {
        "01_Leaders", "Archive", "Members", "Com: FLC", "Com: AC", "Board"}
    assert 200 < len(spec.files) < 400 and all(any(f.drive == d and f.facts for f in spec.files) for d in DRIVES)
    assert len({f.path for f in spec.files}) == len(spec.files)
    assert {f.fmt for f in spec.files} == {"md", "txt", "pdf", "docx", "xlsx", "pptx"}
    assert all(":" not in f.path for f in spec.files)  # valid on Windows too
    assert max(f.path.count("/") for f in spec.files) >= 4  # layered folders


def test_facts_unique_and_answerable(spec):
    qs = [x["question"] for f in spec.files for x in f.facts]
    assert len(qs) == len(set(qs)) > 80
    for f in spec.files:
        for x in f.facts:
            assert x["answer"] in x["sentence"]


def test_policy_loads_and_every_file_has_a_drive(spec):
    policy = Policy(spec.users, spec.drives, spec.shares)
    assert all(policy.drive_of(f.path) == f.drive for f in spec.files)


def test_partial_access_cases_exist(spec):
    """Some fact-bearing files are readable by a non-member only through an individual share."""
    policy = Policy(spec.users, spec.drives, spec.shares)
    cases = [
        (u, f.path) for f in spec.files if f.facts for u in spec.users
        if f.drive not in policy.drives_with_access(u) and policy.can_read(u, f.path)
    ]
    assert len(cases) >= 20


def test_org_wide_folder_inside_restricted_drive(spec):
    policy = Policy(spec.users, spec.drives, spec.shares)
    folder = next(s["path"] for s in spec.shares if s.get("users") == ["*"])
    files = [f for f in spec.files if f.path.startswith(folder + "/")]
    outsider = next(u for u, v in spec.users.items() if v["roles"] == [ROLE_MEMBER])
    assert files and policy.drive_of(folder) not in policy.drives_with_access(outsider)
    assert all(policy.can_read(outsider, f.path) for f in files)


def test_subfolder_shares_go_to_individual_people_and_cover_everything_below(spec):
    policy = Policy(spec.users, spec.drives, spec.shares)
    folders = [s for s in spec.shares if s["path"].count("/") >= 1 and not s["path"].endswith(tuple(f".{x}" for x in ("md", "pdf", "docx", "xlsx", "pptx", "txt"))) and s.get("users") not in (None, ["*"])]
    assert len(folders) >= 8
    for s in folders:
        below = [f.path for f in spec.files if f.path.startswith(s["path"] + "/")]
        assert below, s
        for u in s["users"]:
            assert all(policy.can_read(u, p) for p in below)
    assert any(s.get("roles") == [ROLE_MEMBER] for s in spec.shares)  # and one folder shared to a whole role


def test_roundtrip_all_formats(tmp_path):
    """Template prose, small slice: planted facts and PII survive writing and re-extracting every format."""
    files = build(tmp_path, seed=1, use_llm=False, workers=2)
    assert verify(tmp_path, files) == []


def test_created_dates_valid_and_follow_file_names(spec):
    from datetime import date

    assert all(date.fromisoformat(f.created) <= date(2026, 10, 1) for f in spec.files)
    minutes = next(f for f in spec.files if f.kind == "minutes")
    assert minutes.created[:7] in minutes.path  # YYYY-MM from the file name


def test_drive_meta_written(tmp_path):
    import json

    files = build(tmp_path, seed=1, use_llm=False, workers=2, limit=5)
    meta = json.loads((tmp_path / "drive_meta.json").read_text(encoding="utf-8"))
    assert set(meta) == {f.path for f in files}


def test_facts_mostly_sit_in_files_about_their_own_event(spec):
    facts = [(f, x) for f in spec.files for x in f.facts]
    aligned = [(f, x) for f, x in facts if f.event]
    assert len(aligned) / len(facts) >= 0.75
    for f, x in aligned:
        assert f"{f.event} {f.year}" in x["sentence"], (f.path, x["sentence"])
    assert any(not f.event for f, _ in facts)  # some cross-topic mentions remain


def test_negatives_are_unanswerable_by_construction():
    from kf.corpus.spec import EVENTS, build_negatives

    neg = build_negatives(1)
    assert len(neg) == 35 and neg == build_negatives(1)
    assert {n["kind"] for n in neg} == {"unknown-event", "off-topic"}
    assert not any(e in n["question"] for n in neg for e in EVENTS)


def test_general_questions_point_at_existing_general_files(spec):
    from kf.corpus.spec import build_general

    general = build_general(spec.files, 1)
    assert general == build_general(spec.files, 1) and len(general) == 24
    assert {g["kind"] for g in general} == {"general-association", "general-event"}
    paths = [f.path for f in spec.files]
    for g in general:
        assert g["expected"] and all(any(p.startswith(e) for p in paths) for e in g["expected"]), g


def test_three_kinds_of_people_read_what_they_should(spec):
    policy = Policy(spec.users, spec.drives, spec.shares)
    by_role = lambda r: [u for u, v in spec.users.items() if v["roles"] == [r]]
    assert all(len(v["roles"]) == 1 for v in spec.users.values())  # no one holds two roles
    assert len(by_role(ROLE_BOARD)) == 3 and len(by_role(ROLE_LEADER)) == 4 and len(by_role(ROLE_MEMBER)) == 12
    assert all(policy.drives_with_access(u) == set(spec.drives) for u in by_role(ROLE_BOARD))  # every folder
    for u in by_role(ROLE_LEADER):  # Leaders, Archive, Members and exactly one committee's drive
        opened = policy.drives_with_access(u)
        assert {"leaders", "archive", "members"} <= opened and len(opened & set(ENTITIES)) == 1 and "board" not in opened
    assert all(policy.drives_with_access(u) == {"members"} for u in by_role(ROLE_MEMBER))  # only Members (plus shares)


def test_names_are_ascii(spec):
    assert all(u.isascii() for u in spec.users)
