import json

import pytest
import yaml

from kf import workspace
from kf.perms import Policy


@pytest.fixture
def fragment(tmp_path):
    for rel in ["Members/info/faq.md", "Com_FLC/events/2025/gala.md", "Com_AC/budgets/b.txt", "01_Leaders/notes/n.md", "Board/minutes/m.md", "Archive/old/o.md",
                "Com_FLC/.DS_Store", "loose-file.md"]:
        f = tmp_path / "drive" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("text", encoding="utf-8")
    return tmp_path


def test_init_writes_a_usable_setup_with_the_three_role_kinds(fragment):
    workspace.init(fragment)
    policy = Policy.load(fragment)
    by_roles = {}
    for u in yaml.safe_load((fragment / "users.yaml").read_text(encoding="utf-8"))["users"]:
        by_roles.setdefault(tuple(policy.roles_of(u)), []).append(u)
    assert set(by_roles) == {("test.board",), ("test.leader",), ("test.committee_member",)}
    everything = {"members", "01-leaders", "archive", "board", "com-flc", "com-ac"}
    assert all(policy.drives_with_access(u) == everything for u in by_roles[("test.board",)])
    leaders = [policy.drives_with_access(u) for u in by_roles[("test.leader",)]]
    assert {"members", "01-leaders", "archive"} <= leaders[0] and {frozenset(x - {"members", "01-leaders", "archive"}) for x in leaders} == {frozenset({"com-flc"}), frozenset({"com-ac"})}
    assert all(policy.drives_with_access(u) == {"members"} for u in by_roles[("test.committee_member",)])
    assert policy.drive_name("com-flc") == "Com_FLC"


def test_creation_dates_cover_supported_files_in_drives_only(fragment):
    workspace.init(fragment)
    meta = json.loads((fragment / "drive_meta.json").read_text(encoding="utf-8"))
    assert set(meta) == {"Members/info/faq.md", "Com_FLC/events/2025/gala.md", "Com_AC/budgets/b.txt", "01_Leaders/notes/n.md", "Board/minutes/m.md", "Archive/old/o.md"}


def test_init_does_not_overwrite_unless_forced(fragment):
    workspace.init(fragment)
    with pytest.raises(SystemExit):
        workspace.init(fragment)
    workspace.init(fragment, force=True)


def test_init_without_drive_folders_explains_what_to_do(tmp_path):
    with pytest.raises(SystemExit, match="one folder per shared drive"):
        workspace.init(tmp_path)


def test_pack_refuses_anything_but_a_generated_corpus(tmp_path, fragment):
    with pytest.raises(SystemExit, match="manifest.json is missing"):  # a fragment of real files has no manifest
        workspace.pack(fragment, tmp_path / "x.zip")
    from kf.corpus.generate import build
    data = tmp_path / "gen"
    build(data, seed=1, use_llm=False, workers=2, limit=5)
    workspace.pack(data, tmp_path / "ok.zip")
    import zipfile
    names = zipfile.ZipFile(tmp_path / "ok.zip").namelist()
    assert "testdata/manifest.json" in names and all(n.startswith("testdata/") for n in names)
    next(d for d in (data / "drive").iterdir() if d.is_dir()).joinpath("real-minutes.docx").write_bytes(b"not generated")
    with pytest.raises(SystemExit, match="1 unknown"):
        workspace.pack(data, tmp_path / "bad.zip")
