"""What the permission system and the filemap can tell a user about their own access, without any file content.

Answers "what is my role?", "which drives can I open?" and "what is in the General folder?". Deterministic code builds it
and only readable facts go in: the user's roles, the drives they can open, drives where single files were shared with
them, and, for drives the question names, the folder labels below them. A label summarises every file under its folder,
so it is shown only when the user can read all of them (invariant 8).
"""

import re
from dataclasses import dataclass, field

from kf.pii import strip

MAX_FOLDERS = 20


@dataclass
class Account:
    roles: list
    drives: list  # [(drive_id, name, label)] drives the user can open in full
    shared: list  # names of other drives where individual files were shared with the user
    folders: list = field(default_factory=list)  # [(path, label)] below drives the question names
    unopened: list = field(default_factory=list)  # [(drive_id, name)] drives the question explicitly names but the user cannot open

    def text(self):
        lines = ["Your account (from the permission system, not from files):",
                 "- Your roles: " + (", ".join(self.roles) or "none")]
        lines.append("- Drives you can open: " + ("; ".join(f"{n} - {l}" if l else n for _, n, l in self.drives) or "none"))
        if self.shared:
            lines.append("- Drives where some single files were shared with you: " + ", ".join(self.shared))
        if self.folders:
            lines.append("- Folders in the drives you asked about:")
            lines += [f"  {path}: {label}" for path, label in self.folders]
        lines += [f"- The user asked about the drive {n}. They cannot open it, so what it contains is unknown to you." for _, n in self.unopened]
        return "\n".join(lines)

    def searched(self):
        """The drives a search covered, for the 'nothing found' reply."""
        names = [n for _, n, _ in self.drives]
        text = "I searched the drives you can open (" + ", ".join(names) + ")" if names else "I searched the files you can read"
        return text + (f" and the files shared with you in {', '.join(self.shared)}." if self.shared else ".")


def _named(question, drive_id, name):
    words = [name] + ([drive_id] if len(drive_id) > 2 else [])  # a short id like "it" is also an ordinary word
    return any(re.search(rf"\b{re.escape(w)}\b", question, 0 if len(w) <= 2 else re.I) for w in words)


def _asked_about(question, drive_id, name):
    """'the Finance folder', 'drive Finance': stricter than _named, because a bare 'events' is an ordinary word."""
    words = "|".join(re.escape(w) for w in [name] + ([drive_id] if len(drive_id) > 2 else []))
    return bool(re.search(rf"\b(?:{words})\s+(?:drive|folder)s?\b|\b(?:drive|folder)s?\s+(?:called\s+|named\s+)?(?:{words})\b", question, re.I))


def build(finder, user, question):
    policy, fm = finder.policy, finder.fm
    readable, live = finder._readable_set(user), finder._live_set
    # shortcut: a scan of the live files per folder shown; index files by folder if the corpus grows large
    safe = lambda folder: not any(p.startswith(folder + "/") and p not in readable for p in live)
    open_ids = sorted(policy.drives_with_access(user), key=policy.drive_name)
    drives = []
    for d in open_ids:
        path = policy.drive_path(d)
        label = fm["folders"].get(path, {}).get("description", "") if safe(path) else ""
        drives.append((d, policy.drive_name(d), strip(label)))
    shared = sorted({policy.drive_name(policy.drive_of(p)) for p in readable} - {n for _, n, _ in drives})
    folders = []
    for d, name, _ in drives:
        if _named(question, d, name):
            base = policy.drive_path(d)
            folders += [(path, strip(e["description"])) for path, e in sorted(fm["folders"].items())
                        if path.startswith(base + "/") and safe(path)]
    unopened = [(d, policy.drive_name(d)) for d in policy.drive_ids() if d not in open_ids and _asked_about(question, d, policy.drive_name(d))]
    return Account(policy.roles_of(user), drives, shared, folders[:MAX_FOLDERS], unopened)
