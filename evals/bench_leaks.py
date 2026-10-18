"""Full leak and PII test, no LLM: every user x every question.

    PYTHONPATH=src:evals .venv/bin/python evals/bench_leaks.py [--out evals/leak_test.md]

The domain expert's prompt is the fixed rules, the user's words, and the retriever's passages (the notice is added by
code after the model answers), so scanning finder + retriever output covers everything the model can be shown.
For all 50 users plus the superuser and a guest, over all 229 questions (answerable, unanswerable, general), asserts:
  - every source and passage is a live file the user may read;
  - no planted PII value is in any passage;
  - no 40-character window of any passage occurs only in files the user cannot read;
  - a denial has exactly drive, drive_name and contact_role, and its role is the drive's labelled contact role;
  - the model-facing text never contains the notice wording;
  - the account block (roles, drives, shared drives, folder labels) lists only drives and folders the user may see.
A negative control first proves the scan flags board text shown to a guest. Any failure aborts with the user and question.
"""

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import bench_finder as bf
from kf import account
from kf.expert import notice
from kf.extract import extract_text
from kf.finder import Config
from kf.pii import strip
from kf.retriever import Retriever

squash = lambda s: re.sub(r"\s+", " ", s).strip()
W = 40


def windows_by_path(finder):
    where = defaultdict(set)
    for path in finder.live:
        text = squash(strip(extract_text(finder.root / path)))
        for i in range(max(len(text) - W + 1, 1)):
            where[text[i : i + W]].add(path)
    return where


def has_leak(policy, where, user, text):
    return any(h and not any(policy.can_read(user, x) for x in h) for h in (where.get(text[i : i + W]) for i in range(len(text) - W + 1)))


def check_account(finder, policy, user):
    """The account block holds only what the user may see, even for a question that names every drive."""
    readable = {p for p in finder.live if policy.can_read(user, p)}
    everything = " ".join(policy.drive_name(d) for d in policy.drive_ids()) + " " + " ".join(policy.drive_ids())
    info = account.build(finder, user, everything)
    opened = {d for d, _, _ in info.drives}
    assert opened == policy.drives_with_access(user), f"drives listed for {user!r}"
    assert not set(info.shared) & {n for _, n, _ in info.drives}
    assert set(info.shared) <= {policy.drive_name(policy.drive_of(p)) for p in readable}, f"shared drives for {user!r}"
    hidden = {finder.live[p]["description"] for p in finder.live if p not in readable}
    for path, label in info.folders:
        assert policy.drive_of(path) in opened, f"folder of a drive the user cannot open: {user!r} {path}"
        assert not [p for p in finder.live if p.startswith(path + "/") and p not in readable], f"label of a folder with unreadable files: {user!r} {path}"
    text = info.text()
    assert not [h for h in hidden if h and h in text], f"label of an unreadable file in the account block of {user!r}"
    assert info.roles == policy.roles_of(user)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "leak_test.md"))
    a = ap.parse_args()
    policy, finder, personas, users, _ = bf.load(Config.load("finder.yaml"))
    questions = [q["question"] for name in ("qa.jsonl", "negatives.jsonl", "general.jsonl") for q in bf.read_jsonl(name)]
    planted = [squash(x["value"]) for x in json.loads((bf.DATA / "pii.json").read_text(encoding="utf-8"))]
    where = windows_by_path(finder)
    retriever = Retriever(finder)
    # negative control: the scan must flag board text shown to a guest, and not to the superuser
    board = next(p for p in sorted(finder.live) if p.startswith("Board/") and p.endswith(".md"))
    sample = squash(strip(extract_text(finder.root / board)))[:600]
    assert has_leak(policy, where, "guest", sample) and not has_leak(policy, where, "superuser", sample), "leak scan is broken"
    totals = dict(users=0, finds=0, sources=0, passages=0, notices=0, empty=0)
    t0 = time.perf_counter()
    for user in sorted(users):
        totals["users"] += 1
        check_account(finder, policy, user)
        for question in questions:
            result = finder.find(user, question)
            passages = retriever.retrieve(user, question, result)
            assert not retriever.dropped, (user, question, retriever.dropped)
            where_ = f"user {user!r}, question {question!r}"
            for s in result.sources:
                assert s.path in finder.live and policy.can_read(user, s.path), f"unreadable source: {where_}"
            for p in passages:
                assert p.path in finder.live and policy.can_read(user, p.path), f"unreadable passage: {where_}"
                text = squash(p.text)
                assert not [v for v in planted if v in text], f"PII in a passage: {where_}"
                assert not has_leak(policy, where, user, text), f"text of an unreadable file: {where_}"
                assert notice_free(text), where_
            if result.denial:
                d = result.denial
                assert set(vars(d)) == {"drive", "drive_name", "contact_role"}, where_
                assert d.contact_role == policy.contact_role(d.drive) and d.drive_name == policy.drive_name(d.drive), where_
                totals["notices"] += 1
            totals["finds"] += 1
            totals["sources"] += len(result.sources)
            totals["passages"] += len(passages)
            totals["empty"] += not passages
    secs = time.perf_counter() - t0
    text = (f"# Leak and PII test (no LLM)\n\nAll assertions held: {totals['users']} users ({totals['users'] - 2} test people, a superuser and a guest) x "
            f"{len(questions)} questions = {totals['finds']} finder + retriever runs in {secs:.0f} s.\n\n"
            f"- sources returned: {totals['sources']}, passages built: {totals['passages']}, runs with no passage: {totals['empty']}, "
            f"denial notices: {totals['notices']}\n"
            f"- every source and passage readable by its user and live; no planted PII value in any passage; no 40-character window "
            f"of a passage that exists only in files the user cannot read; every notice has exactly drive, name and the labelled contact role; the account block lists only what the user may see.\n")
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


def notice_free(text):
    return "do not have permission" not in text


if __name__ == "__main__":
    main()
