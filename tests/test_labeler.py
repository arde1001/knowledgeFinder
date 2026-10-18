import pytest

from kf import filemap
from kf.labeler import build_filemap
from kf.perms import Policy

USERS = {"bob": {"roles": ["events"]}}
DRIVES = {
    "events": {"name": "Events", "path": "events", "members": {"roles": ["events"]}, "contact_role": "Events lead"},
    "general": {"name": "General", "path": "general", "members": {"roles": ["*"]}, "contact_role": "Secretary"},
}
FILES = {"events/plans/gala.md": "Gala plan text", "events/plans/picnic.txt": "Picnic text", "general/info/faq.md": "FAQ text"}
META = {p: {"created": "2025-03-14"} for p in FILES}


class Counter:
    def __init__(self):
        self.files, self.folders = 0, 0

    def describe(self, path, text):
        self.files += 1
        return f"About {path}"

    def summarize(self, folder, lines):
        self.folders += 1
        return f"Folder {folder}"


@pytest.fixture
def root(tmp_path):
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def build(root, policy=None, meta=META, old=None, c=None, **kw):
    c = c or Counter()
    fm, stats = build_filemap(root, meta, policy or Policy(USERS, DRIVES, []), c.describe, c.summarize, old=old, **kw)
    return fm, stats, c


def test_entries_are_complete_and_folders_labelled(root):
    fm, stats, _ = build(root)
    assert stats["labelled"] == 3
    e = fm["files"]["events/plans/gala.md"]
    assert filemap.is_complete(e) and e["type"] == "md" and e["created"] == "2025-03-14"
    assert e["permissions"]["drive"] == "events" and e["permissions"]["members"]["roles"] == ["events"]
    assert set(fm["folders"]) == {"events", "events/plans", "general", "general/info"}


def test_unlabellable_files_are_left_out(root):
    (root / "events/plans/scan.png").write_bytes(b"x")  # unsupported type
    (root / "events/plans/nodate.md").write_text("x", encoding="utf-8")  # no creation date
    (root / "orphan").mkdir()
    (root / "orphan/x.md").write_text("x", encoding="utf-8")  # not in any drive
    meta = {**META, "events/plans/scan.png": {"created": "2025-01-01"}, "orphan/x.md": {"created": "2025-01-01"}}
    fm, stats, _ = build(root, meta=meta)
    assert set(fm["files"]) == set(FILES) and stats["skipped"] == 3


def test_description_with_pii_is_rejected(root):
    c = Counter()
    c.describe = lambda path, text: "Contact anna@example.org for details"
    fm, _, _ = build(root, c=c)
    assert fm["files"] == {}  # nothing labelled, nothing findable


def test_rerun_reuses_unchanged_files_and_folders(root):
    fm, _, _ = build(root)
    c = Counter()
    fm2, stats, _ = build(root, old=fm, c=c)
    assert (c.files, c.folders, stats["reused"]) == (0, 0, 3)
    assert fm2["files"] == fm["files"]


def test_in_file_edit_keeps_file_findable_and_rerun_relabels(root):
    policy = Policy(USERS, DRIVES, [])
    fm, _, _ = build(root, policy)
    (root / "events/plans/gala.md").write_text("Completely different text", encoding="utf-8")
    assert "events/plans/gala.md" in filemap.live_files(fm, policy, root)
    c = Counter()
    build(root, policy, old=fm, c=c)
    assert c.files == 1


def test_permission_change_drops_file_until_relabelled(root):
    fm, _, _ = build(root)
    shared = Policy(USERS, DRIVES, [{"path": "events/plans/gala.md", "users": ["bob"]}])
    live = filemap.live_files(fm, shared, root)
    assert "events/plans/gala.md" not in live and "events/plans/picnic.txt" in live
    fm2, _, c = build(root, shared, old=fm)
    assert c.files == 0  # content unchanged, description reused; only permissions refreshed
    assert "events/plans/gala.md" in filemap.live_files(fm2, shared, root)


def test_moved_file_is_dropped_and_new_location_unlabelled(root):
    policy = Policy(USERS, DRIVES, [])
    fm, _, _ = build(root, policy)
    (root / "events/archive").mkdir()
    (root / "events/plans/gala.md").rename(root / "events/archive/gala.md")
    live = filemap.live_files(fm, policy, root)
    assert "events/plans/gala.md" not in live and "events/archive/gala.md" not in live


def test_incomplete_or_tampered_entries_are_not_live(root):
    policy = Policy(USERS, DRIVES, [])
    fm, _, _ = build(root, policy)
    fm["files"]["general/info/faq.md"]["description"] = ""
    fm["files"]["events/plans/picnic.txt"]["created"] = "not a date"
    fm["files"]["../etc/passwd"] = {**fm["files"]["events/plans/gala.md"]}
    assert set(filemap.live_files(fm, policy, root)) == {"events/plans/gala.md"}


def test_markdown_rendering_lists_every_file(root):
    fm, _, _ = build(root)
    md = filemap.render_md(fm)
    assert all(rel.rpartition("/")[2] in md for rel in FILES) and "Folder events/plans" in md
