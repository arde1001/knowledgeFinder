"""Admin helper for testing on a fragment of the real files (downloaded as a plain folder tree, not from Google Drive).

    python -m kf.workspace init  --data mydata    # mydata/drive/<Drive folder>/... exists; writes the rest of the test setup
    python -m kf.workspace users --data mydata    # who exists, with which roles, and which drives they can open
    python -m kf.workspace pack  --data testdata  # zip a GENERATED synthetic corpus (labels, indexes) for sharing

Every top-level folder under <data>/drive is one shared drive. `init` writes drives.yaml, users.yaml, shares.yaml and
drive_meta.json (creation dates), which an export does not carry. Roles follow the demo model: test.board opens every
drive, test.leader opens Leaders, Archive and the own committee's drive (named as a member of that drive), and
test.committee_member opens only the drive named Members (or General), which is open to everyone. Any other folder is a
committee drive. The users are invented test people. Edit the files afterwards (above all the
contact_role of each drive) and run the labeler and indexer. Never writes outside <data>.
"""

import argparse
import json
import random
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import yaml

from kf.corpus.spec import FIRST, LAST, ROLE_BOARD, ROLE_LEADER, ROLE_MEMBER
from kf.extract import SUFFIXES
from kf.perms import Policy

MEMBERS_PER_DRIVE = 2


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "drive"


def init(data, force=False, seed=1):
    data = Path(data)
    root = data / "drive"
    folders = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []
    if not folders:
        raise SystemExit(f"no drive folders found: put one folder per shared drive under {root}")
    targets = [data / n for n in ("drives.yaml", "users.yaml", "shares.yaml", "drive_meta.json")]
    if not force and any(t.exists() for t in targets):
        raise SystemExit("drives.yaml, users.yaml, shares.yaml or drive_meta.json already exist; pass --force to overwrite them")
    everyone, shared_with_leaders = ("members", "general"), ("archive",)
    drives = {}
    for name in folders:
        i = slug(name)
        roles = ["*"] if i in everyone else [ROLE_LEADER, ROLE_BOARD] if i in shared_with_leaders or "leaders" in i else [ROLE_BOARD]
        drives[i] = {"name": name, "path": name, "members": {"roles": roles}, "contact_role": f"Owner of {name}"}
    rng = random.Random(seed)
    names = set()

    def person(role):
        while True:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            if (first, last) not in names:
                names.add((first, last))
                return f"{first}.{last}".lower(), {"roles": [role]}

    users = dict(person(ROLE_BOARD) for _ in range(MEMBERS_PER_DRIVE))
    for i, d in drives.items():
        if d["members"]["roles"] == [ROLE_BOARD] and i != "board":  # a committee drive: one leader reads it by name, plus two members
            leader = person(ROLE_LEADER)
            d["members"]["users"] = [leader[0]]
            users.update([leader] + [person(ROLE_MEMBER) for _ in range(MEMBERS_PER_DRIVE)])
    meta = {}
    for f in sorted(root.rglob("*")):
        # shortcut: file modification time stands in for Drive's createdTime; supply the real dates here when the export has them
        if f.is_file() and f.suffix.lower() in SUFFIXES and f.relative_to(root).parts[0] in folders:
            meta[f.relative_to(root).as_posix()] = {"created": datetime.fromtimestamp(f.stat().st_mtime).date().isoformat()}
    dump = lambda name, obj: (data / name).write_text(yaml.safe_dump(obj, sort_keys=True, allow_unicode=True), encoding="utf-8")
    dump("drives.yaml", {"drives": drives})
    dump("users.yaml", {"users": users})
    dump("shares.yaml", {"shares": []})
    (data / "drive_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    Policy.load(data)  # fails loudly if the setup is not usable
    print(f"{len(drives)} drives, {len(users)} test users, {len(meta)} files with a creation date -> {data}")
    print("Next: edit contact_role in drives.yaml, then run the labeler and the indexer.")


def show_users(data):
    policy = Policy.load(data)
    users = yaml.safe_load((Path(data) / "users.yaml").read_text(encoding="utf-8"))["users"]
    print(f"{'user':28} {'roles':26} drives they can open")
    for u in sorted(users):
        opened = ", ".join(policy.drive_name(d) for d in sorted(policy.drives_with_access(u)))
        print(f"{u:28} {'+'.join(policy.roles_of(u)) or '-':26} {opened}")


BUNDLE = ["drive", "index", "drive_meta.json", "drives.yaml", "users.yaml", "shares.yaml", "filemap.json", "filemap.md",
          "manifest.json", "qa.jsonl", "negatives.jsonl", "general.jsonl", "paraphrases.jsonl", "pii.json"]


def pack(data, out):
    """Zip a corpus written by kf.corpus.generate, as testdata/... Real files must never leave the machine, so every file
    under drive/ has to be one the generator listed in manifest.json."""
    data = Path(data)
    manifest = data / "manifest.json"
    if not manifest.exists():
        raise SystemExit(f"{manifest} is missing: only a corpus made by kf.corpus.generate can be packed")
    listed = {f["path"] for f in json.loads(manifest.read_text(encoding="utf-8"))}
    on_disk = {f.relative_to(data / "drive").as_posix() for f in (data / "drive").rglob("*") if f.is_file()}
    if on_disk != listed:
        raise SystemExit(f"drive/ does not match the generator's manifest ({len(on_disk - listed)} unknown, "
                         f"{len(listed - on_disk)} missing files): refusing to pack")
    # labels and index chunks carry text too: a file labelled or indexed once and deleted since would still ship
    labelled = json.loads((data / "filemap.json").read_text(encoding="utf-8")) if (data / "filemap.json").exists() else {}
    folders = {"/".join(p.split("/")[:i]) for p in listed for i in range(1, p.count("/") + 1)}
    stale = (set(labelled.get("files", {})) - listed) | (set(labelled.get("folders", {})) - folders)
    for chunks in (data / "index").rglob("chunks.json") if (data / "index").is_dir() else []:
        stale |= {c["path"] for c in json.loads(chunks.read_text(encoding="utf-8"))["chunks"]} - listed
    if stale:
        raise SystemExit(f"labels or indexes name {len(stale)} paths the generator did not write: refusing to pack")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in BUNDLE:
            p = data / name
            for f in [p] if p.is_file() else sorted(p.rglob("*")) if p.is_dir() else []:
                if f.is_file():
                    z.write(f, (Path("testdata") / f.relative_to(data)).as_posix())
    print(f"{out}: {Path(out).stat().st_size / 1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["init", "users", "pack"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--force", action="store_true", help="init: overwrite existing setup files")
    ap.add_argument("--out", default="kf-testdata.zip", help="pack: the zip to write")
    a = ap.parse_args()
    if a.command == "pack":
        return pack(a.data, a.out)
    init(a.data, a.force) if a.command == "init" else show_users(a.data)


if __name__ == "__main__":
    sys.exit(main())
