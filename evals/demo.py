"""Scripted persona demo for non-technical members: the same questions asked as six different people.

    PYTHONPATH=src:evals .venv/bin/python evals/demo.py [--out evals/demo_transcript.md]

Personas: a Board member (reads every drive), a leader of the FLC committee, a leader of the AC committee, a committee member, a committee member who
was shared a few folders and files from other drives, and a guest with no role. Questions are chosen by rule from the test corpus
(a Board-only fact, a Leaders-only fact, a fact in the FLC committee's drive, a fact in a file shared with the sharee, a general question, an
unanswerable question, and a follow-up) and, for the demo, only questions the superuser (a stand-in for "reads everything", never shown)
answers correctly (and, for restricted ones, where the notice appears) are used, so every difference between people is a permission difference. The benchmarks, not this script, measure accuracy.
Everything shown is the user-visible reply: answer, sources, and the drive-level notice.
"""

import argparse
import re
from pathlib import Path

import bench_finder as bf
from kf.corpus.spec import ROLE_BOARD
from kf.expert import Expert

squash = lambda s: re.sub(r"\s+", " ", s).strip().lower()
EVENT = re.compile(r"(?:[A-Z][a-z]+ )+20\d\d")


def pick(items, expert, policy, personas):
    """First item the superuser answers correctly and whose drive is named to every persona who cannot read it
    (else the best of the first 12): a demo should show the typical case, the benchmark shows how often it happens."""
    best = None
    for item in items[:12]:
        expert.reset()
        if squash(item["answer"]) not in squash(expert.ask("superuser", item["question"]).answer):
            continue
        blocked = [u for _, u in personas if not policy.can_read(u, item["path"])]
        fired = 0
        for u in blocked:
            expert.reset()
            d = expert.ask(u, item["question"]).denial
            fired += bool(d) and d.drive == policy.drive_of(item["path"])
        score = fired / len(blocked) if blocked else 1
        best = (score, item) if best is None or score > best[0] else best
        if score == 1:
            break
    if best is None:
        raise SystemExit("no usable demo question")
    return best[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "demo_transcript.md"))
    a = ap.parse_args()
    policy, finder, base, users, _ = bf.load(bf.config())
    expert = Expert(finder)
    qa = bf.read_jsonl("qa.jsonl")
    general = [g for g in bf.read_jsonl("general.jsonl") if g["kind"] == "general-association"]
    negatives = bf.read_jsonl("negatives.jsonl")
    board_user = next(u for u in sorted(users) if users[u]["roles"] == [ROLE_BOARD])
    sharee = base["sharee"]
    sharee_drives = policy.drives_with_access(sharee)
    personas = [("Board member (reads every drive)", board_user), ("Leader of Com: FLC", base["leader"]),
                ("Leader of Com: AC", base["other_leader"]), ("Committee member", base["member"]),
                ("Committee member with some shared folders", sharee), ("Guest (no role)", "guest")]

    in_drive = lambda d: [i for i in qa if i["drive"] == d and i["aligned"]]
    shared = [i for i in qa if i["aligned"] and policy.can_read(sharee, i["path"]) and policy.drive_of(i["path"]) not in sharee_drives]
    questions = [("A fact that lives in the Board drive", pick(in_drive("board"), expert, policy, personas)["question"]),
                 ("A fact that lives in the Leaders drive", pick(in_drive("leaders"), expert, policy, personas)["question"]),
                 ("A fact that lives in the Com: FLC drive", pick(in_drive("com_flc"), expert, policy, personas)["question"])]
    if shared:
        questions.append(("A fact in a folder that was shared with one member", pick(shared, expert, policy, personas)["question"]))
    questions += [("A general question about the association", general[0]["question"]),
                  ("A question about something that does not exist", negatives[0]["question"])]

    events = {}  # facts about the same event in the same drive; the FLC drive first
    for i in qa:
        m = EVENT.search(i["question"])
        if m:
            events.setdefault((i["drive"] != "com_flc", i["drive"], m.group(0)), []).append(i)
    pair = next(v for _, v in sorted(events.items()) if len({x["key"] for x in v}) > 1)
    first, second = pair[0], next(x for x in pair if x["key"] != pair[0]["key"])
    follow = "And " + second["question"][0].lower() + second["question"][1:]
    event = EVENT.search(second["question"]).group(0)
    follow = follow.replace("the " + event, "that event").replace(event, "that event")

    out = ["# Demo: the same questions, six different people\n",
           "Each person asks the domain expert the same questions. The expert only ever sees files that person may read. "
           "When the best match sits in a drive they cannot open, they are told which drive and whom to ask, and nothing more. "
           "Questions were chosen so that someone who reads everything answers them correctly and, where someone cannot read the file, so the notice appears; it appears for roughly three in four such questions, not all (see the benchmark files).\n"]
    for title, question in questions:
        out.append(f"## {title}\n\n> {question}\n")
        for label, user in personas:
            expert.reset()
            out.append(f"**{label}**\n\n{indent(expert.ask(user, question).text)}\n")
    out.append(f"## A follow-up question\n\n> 1. {first['question']}\n> 2. {follow}\n")
    for label, user in personas:
        expert.reset()
        r1 = expert.ask(user, first["question"])
        r2 = expert.ask(user, follow)
        out.append(f"**{label}**\n\n1. {indent(r1.text, first=False)}\n\n   (the second question was understood as: *{r2.query}*)\n\n2. {indent(r2.text, first=False)}\n")
    Path(a.out).write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


def indent(text, first=True):
    lines = text.splitlines()
    pad = "> " if first else "   > "
    return "\n".join((pad if i or first else "> ") + l if l else pad.rstrip() for i, l in enumerate(lines))


if __name__ == "__main__":
    main()
