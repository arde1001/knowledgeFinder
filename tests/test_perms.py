import pytest

from kf.perms import Policy

USERS = {
    "alice": {"roles": ["board"]},
    "bob": {"roles": ["events"]},
    "carol": {"roles": ["events", "finance"]},
    "dave": {"roles": []},
}
DRIVES = {
    "general": {"name": "General", "path": "general", "members": {"roles": ["*"]}, "contact_role": "Secretary"},
    "board": {"name": "Board", "path": "board", "members": {"roles": ["board"]}, "contact_role": "Chairperson"},
    "events": {"name": "Events", "path": "events", "members": {"roles": ["events"]}, "contact_role": "Events lead"},
    "finance": {"name": "Finance", "path": "finance", "members": {"roles": ["finance"]}, "contact_role": "Treasurer"},
}
SHARES = [
    {"path": "board/minutes/2025-03.pdf", "users": ["dave"]},  # single file shared to an outsider
    {"path": "finance/budgets", "roles": ["events"]},  # folder shared to a role
    {"path": "events/2025", "users": ["*"]},  # org-wide folder inside a restricted drive
]


@pytest.fixture
def policy():
    return Policy(USERS, DRIVES, SHARES)


def test_member_role_reads_own_drive_and_descendants(policy):
    assert policy.can_read("bob", "events/2024/plan.md")
    assert policy.can_read("bob", "events")


def test_non_member_denied(policy):
    assert not policy.can_read("bob", "board/agenda.md")
    assert not policy.can_read("dave", "events/2024/plan.md")


def test_everyone_drive_wildcard(policy):
    assert policy.can_read("dave", "general/handbook.md")


def test_multiple_roles_are_a_union(policy):
    assert policy.can_read("carol", "events/x.md")
    assert policy.can_read("carol", "finance/x.md")
    assert not policy.can_read("carol", "board/x.md")


def test_file_share_grants_only_that_file(policy):
    assert policy.can_read("dave", "board/minutes/2025-03.pdf")
    assert not policy.can_read("dave", "board/minutes/2025-04.pdf")
    assert not policy.can_read("dave", "board/minutes/2025-03.pdf.bak")


def test_folder_share_covers_descendants_not_siblings(policy):
    assert policy.can_read("bob", "finance/budgets/2025/events.xlsx")
    assert not policy.can_read("bob", "finance/payroll/2025.xlsx")


def test_share_does_not_match_name_prefix(policy):
    assert not policy.can_read("bob", "finance/budgets-secret/x.xlsx")


def test_org_wide_item_inside_restricted_drive(policy):
    assert policy.can_read("dave", "events/2025/programme.md")
    assert not policy.can_read("dave", "events/2024/programme.md")


def test_unknown_drive_and_unknown_user_denied(policy):
    assert not policy.can_read("alice", "nowhere/x.md")
    assert not policy.can_read("mallory", "general/handbook.md")


@pytest.mark.parametrize("path", ["", "/", "/general/x.md", "general/../board/x.md", "general\\..\\board", "../board/x.md"])
def test_unsafe_or_empty_paths_denied(policy, path):
    assert not policy.can_read("alice", path)


def test_redundant_separators_normalised(policy):
    assert policy.can_read("bob", "events//2024/./plan.md")
    assert not policy.can_read("bob", "board//x.md")


def test_drive_info(policy):
    assert policy.drive_of("events/2024/plan.md") == "events"
    assert policy.drive_of("nowhere/x.md") is None
    assert policy.drive_name("board") == "Board"
    assert policy.contact_role("board") == "Chairperson"


def test_readable_drives_for_listing(policy):
    assert policy.drives_with_access("bob") == {"general", "events"}
    assert policy.drives_with_access("dave") == {"general"}  # file shares don't grant drive access


def test_access_descriptor_lists_drive_members_and_covering_shares(policy):
    d = policy.access_descriptor("finance/budgets/2025/events.xlsx")
    assert d["drive"] == "finance"
    assert d["members"] == {"roles": ["finance"], "users": []}
    assert d["shares"] == [{"path": "finance/budgets", "roles": ["events"], "users": []}]
    assert policy.access_descriptor("finance/payroll/x.xlsx")["shares"] == []
    assert policy.access_descriptor("nowhere/x.md") is None


def test_fingerprint_tracks_permission_changes_only(policy):
    path = "board/minutes/2025-03.pdf"
    base = policy.fingerprint(path)
    assert base == Policy(USERS, DRIVES, SHARES).fingerprint(path)
    # a user's roles are not part of the file's permissions
    assert base == Policy({**USERS, "bob": {"roles": ["board"]}}, DRIVES, SHARES).fingerprint(path)
    # unrelated share: same; share added or removed on the file: different
    assert base == Policy(USERS, DRIVES, SHARES + [{"path": "events/2024", "users": ["bob"]}]).fingerprint(path)
    assert base != Policy(USERS, DRIVES, SHARES + [{"path": path, "users": ["bob"]}]).fingerprint(path)
    assert base != Policy(USERS, DRIVES, SHARES[1:]).fingerprint(path)
    # drive membership change: different
    moved = {**DRIVES, "board": {**DRIVES["board"], "members": {"roles": ["board", "events"]}}}
    assert base != Policy(USERS, moved, SHARES).fingerprint(path)


def test_load_rejects_drive_without_contact_role():
    bad = {"x": {"name": "X", "path": "x", "members": {"roles": []}}}
    with pytest.raises(ValueError, match="contact_role"):
        Policy(USERS, bad, [])
