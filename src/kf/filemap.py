"""The filemap: the only list of files the finder may use. Written by the labeler (admin), read-only elsewhere.

{"generated", "model", "files": {path: entry}, "folders": {path: {"description", "inputs_hash"}}}
entry = {"created", "type", "description", "permissions", "permissions_hash", "content_hash"}
content_hash only lets the labeler skip relabelling unchanged files; it plays no part in findability.
"""

import json
from datetime import date
from pathlib import Path

REQUIRED = ("created", "type", "description", "permissions", "permissions_hash")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(fm, path):
    path = Path(path)
    path.write_text(json.dumps(fm, indent=1, ensure_ascii=False), encoding="utf-8")
    path.with_suffix(".md").write_text(render_md(fm), encoding="utf-8")


def is_complete(entry):
    try:
        date.fromisoformat(entry["created"])
    except (KeyError, TypeError, ValueError):
        return False
    return all(entry.get(k) for k in REQUIRED)


def live_files(fm, policy, root):
    """Entries the finder may use now: completely labelled, still at their path, permissions unchanged since labelling.

    In-file edits do not matter. A moved file is a new path, so it is absent until the labeler is rerun.
    """
    return {
        p: e for p, e in fm["files"].items()
        if is_complete(e) and (Path(root) / p).is_file() and policy.fingerprint(p) == e["permissions_hash"]
    }


def perm_summary(perm):
    members = ", ".join(perm["members"]["roles"] + perm["members"]["users"]) or "nobody"
    shares = "; ".join(f"{s['path']} -> {', '.join(s['roles'] + s['users'])}" for s in perm["shares"])
    return f"drive {perm['drive']} members: {members}" + (f"; shares: {shares}" if shares else "")


def render_md(fm):
    """Human-readable version for the administrator to verify."""
    by_folder = {}
    for path in fm["files"]:
        folder, _, name = path.rpartition("/")
        by_folder.setdefault(folder, []).append((name, fm["files"][path]))
    out = [f"# Filemap\n\ngenerated {fm.get('generated', '?')} with {fm.get('model', '?')}; {len(fm['files'])} files"]
    for folder in sorted(set(fm["folders"]) | set(by_folder)):
        label = fm["folders"].get(folder, {}).get("description", "")
        out.append(f"\n{'#' * min(folder.count('/') + 2, 4)} {folder}\n\n{label}\n")
        for name, e in sorted(by_folder.get(folder, ())):
            out.append(f"- `{name}` ({e['type']}, created {e['created']}) {e['description']}\n  access: {perm_summary(e['permissions'])}")
    return "\n".join(out) + "\n"
