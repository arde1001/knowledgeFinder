"""Admin tool: label every file and folder and write the filemap. Never runs on the question path.

    PYTHONPATH=src .venv/bin/python -m kf.labeler --data testdata [--workers 4] [--limit N]

A file is labelled only if it has a creation date, a drive, a supported type and a PII-free description; anything
else is left out of the filemap (and so can never be found). Rerunning keeps descriptions of files whose content is
unchanged, and refreshes their permissions.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from kf import filemap, llm
from kf.extract import SUFFIXES, extract_text
from kf.pii import contains_pii
from kf.perms import Policy

TEXT_LIMIT = 3000  # characters of a file shown to the model


def _one_line(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"[*#`]+", "", text)).strip().strip("\"'")[:300]


def _usable(text):
    return bool(text) and not contains_pii(text)


def _ask(prompt):
    for attempt in range(2):
        out = _one_line(llm.chat([{"role": "user", "content": prompt}], temperature=0.2 * attempt, max_tokens=120))
        if _usable(out):
            return out
    raise ValueError("no usable description")


def llm_describe(path, text):
    return _ask(
        f"File: {path}\n\nContent (may be cut off):\n{text}\n\n"
        "Write ONE sentence (at most 30 words) saying what this document is and which events, topics or "
        "activities it concerns, so that someone searching can tell whether it is relevant. "
        "Do not include email addresses, phone numbers, street addresses or bank accounts. Output only the sentence."
    )


def llm_summarize(folder, lines):
    return _ask(
        f"Folder: {folder}\n\nItems in this folder:\n" + "\n".join(lines) + "\n\n"
        "Write ONE sentence (at most 30 words) saying what kind of material this folder holds and which topics "
        "it covers. Do not include email addresses, phone numbers, street addresses or bank accounts. "
        "Output only the sentence."
    )


def build_filemap(root, meta, policy, describe=llm_describe, summarize=llm_summarize, old=None, workers=4,
                  model="", files=None, log=lambda *a: None):
    root = Path(root)
    old_files = (old or {}).get("files", {})
    old_folders = (old or {}).get("folders", {})
    stats = {"labelled": 0, "reused": 0, "skipped": 0}

    def label(rel):
        path = root / rel
        created = meta.get(rel, {}).get("created", "")
        perms = policy.access_descriptor(rel)
        try:
            date.fromisoformat(created)
        except ValueError:
            created = ""
        if path.suffix.lower() not in SUFFIXES or not created or perms is None:
            log("skip", rel)
            return rel, None
        chash = hashlib.sha256(path.read_bytes()).hexdigest()
        prev = old_files.get(rel, {})
        try:
            if prev.get("content_hash") == chash and prev.get("description"):
                description, reused = prev["description"], True
            else:
                description, reused = describe(rel, extract_text(path)[:TEXT_LIMIT]), False
            if not _usable(description):
                raise ValueError("unusable description")
        except Exception as exc:  # unlabelled files stay out of the filemap
            log("fail", rel, exc)
            return rel, None
        return rel, {
            "created": created, "type": path.suffix.lower().lstrip("."), "description": description,
            "permissions": perms, "permissions_hash": policy.fingerprint(rel), "content_hash": chash, "_reused": reused,
        }

    rels = files if files is not None else sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    with ThreadPoolExecutor(workers) as pool:
        entries = {}
        for rel, entry in pool.map(label, rels):
            if entry is None:
                stats["skipped"] += 1
                continue
            stats["reused" if entry.pop("_reused") else "labelled"] += 1
            entries[rel] = entry

    # folders, deepest first, so each summary can use its subfolders' summaries
    folders = {}
    all_dirs = {"/".join(p.split("/")[:i]) for p in entries for i in range(1, p.count("/") + 1)}
    for depth in sorted({d.count("/") for d in all_dirs}, reverse=True):
        level = [d for d in all_dirs if d.count("/") == depth]

        def summarise(folder):
            lines = sorted(
                [f"{p.rpartition('/')[2]}: {e['description']}" for p, e in entries.items() if p.rpartition("/")[0] == folder]
                + [f"{d.rpartition('/')[2]}/: {folders[d]['description']}" for d in folders if d.rpartition("/")[0] == folder]
            )
            inputs = hashlib.sha1("\n".join(lines).encode()).hexdigest()
            prev = old_folders.get(folder, {})
            if prev.get("inputs_hash") == inputs and prev.get("description"):
                return folder, {"description": prev["description"], "inputs_hash": inputs}
            try:
                description = summarize(folder, lines)
                if not _usable(description):
                    raise ValueError("unusable description")
                return folder, {"description": description, "inputs_hash": inputs}
            except Exception as exc:
                log("fail", folder, exc)
                return folder, None

        with ThreadPoolExecutor(workers) as pool:
            folders.update({f: v for f, v in pool.map(summarise, level) if v})

    fm = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model,
          "files": entries, "folders": folders}
    return fm, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="testdata", help="folder with drive/, users.yaml, drives.yaml, shares.yaml, drive_meta.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, help="only the first N files (smoke test)")
    a = ap.parse_args()
    data = Path(a.data)
    out = data / "filemap.json"
    old = filemap.load(out) if out.exists() else None
    meta = json.loads((data / "drive_meta.json").read_text(encoding="utf-8"))
    root = data / "drive"
    rels = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    t0 = time.time()
    fm, stats = build_filemap(
        root, meta, Policy.load(data), old=old, workers=a.workers, model=llm.CHAT_MODEL,
        files=rels[: a.limit] if a.limit else None, log=lambda *x: print(*x, file=sys.stderr, flush=True),
    )
    filemap.save(fm, out)
    print(f"{stats} folders={len(fm['folders'])} in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
