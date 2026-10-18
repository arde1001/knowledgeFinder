"""Domain-expert benchmark: real model, real prompts.

    PYTHONPATH=src .venv/bin/python evals/bench_expert.py [--per-persona 40] [--pairs 30] [--out evals/expert_benchmark.md]

Hard assertions on every prompt sent to the model (the leak and PII tests of the project):
  - no planted PII value;
  - no label of a file or folder the persona may not see;
  - no 40-character window of text that exists only in files the persona cannot read;
  - the denial notice never appears in a prompt (the drive's name alone can: ordinary words like "Marketing" are in the files);
  - every notice is exactly `notice(denial)`, its labelled contact role.
Measured: answer correctness (planted answer in the reply), correct file cited, refusals on unanswerable questions,
latency, and follow-up rewriting (a question with the event name replaced by "that event", asked after a question
about the same event).
"""

import argparse
import json
import random
import re
import statistics
import time
from pathlib import Path

import bench_finder as bf
from kf.expert import NOTHING, Expert, notice
from kf.extract import extract_text
from kf.finder import Config
from kf.pii import strip

squash = lambda s: re.sub(r"\s+", " ", s).strip()
EVENT = re.compile(r"(?:[A-Z][a-z]+ )+20\d\d")
W = 40


def windows(text, step):
    return {text[i : i + W] for i in range(0, max(len(text) - W + 1, 1), step)}


def shingles(finder, policy, user):
    """40-char windows of text that only unreadable files contain."""
    readable, restricted = set(), set()
    for path in finder.live:
        text = squash(strip(extract_text(finder.root / path)))
        (readable if policy.can_read(user, path) else restricted).update(windows(text, 1 if policy.can_read(user, path) else 20))
    return restricted - readable


def hidden_labels(finder, policy, user):
    """Labels of files and folders the user must not see, minus any text that is also a label they may see."""
    readable = {p for p in finder.live if policy.can_read(user, p)}
    shown = {squash(e["description"]) for p, e in finder.live.items() if p in readable}
    shown |= {squash(f["description"]) for k, f in finder.fm["folders"].items() if not any(p.startswith(k + "/") and p not in readable for p in finder.live)}
    hidden = {squash(e["description"]) for p, e in finder.live.items() if p not in readable}
    hidden |= {squash(f["description"]) for k, f in finder.fm["folders"].items() if any(p.startswith(k + "/") and p not in readable for p in finder.live)}
    return {h for h in hidden - shown if h}


def check_prompts(answer, question, policy, secrets, planted, labels=()):
    sent = squash(" ".join(m["content"] for messages in answer.prompts for m in messages))
    assert not [v for v in planted if v in sent], "PII reached the model"
    # the user's own words may legitimately repeat a phrase from a file they cannot read
    seen = windows(sent, 1) - windows(squash(question), 1) - windows(squash(answer.query), 1)
    assert not (seen & secrets), "text from an unreadable file reached the model"
    assert not [l for l in labels if l in sent], "a label the user must not see reached the model"
    if answer.denial:
        d = answer.denial
        assert d.contact_role == policy.contact_role(d.drive) and answer.text.endswith(notice(d))
        assert "do not have permission" not in sent and notice(d) not in sent, "the denial notice reached the model"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=40)
    ap.add_argument("--pairs", type=int, default=30)
    ap.add_argument("--out", default=str(Path(__file__).parent / "expert_benchmark.md"))
    a = ap.parse_args()
    policy, finder, personas, users, _ = bf.load(Config.load("finder.yaml"))
    qa, negatives, general = bf.read_jsonl("qa.jsonl"), bf.read_jsonl("negatives.jsonl"), bf.read_jsonl("general.jsonl")
    planted = [squash(x["value"]) for x in json.loads((bf.DATA / "pii.json").read_text(encoding="utf-8"))]
    rng = random.Random(0)
    rows = ["| persona | readable q | answer correct | right file cited | restricted q | notice names the answer's drive | unanswerable q | refused | general q | cites an expected file | s per question (mean / p95) |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, user in personas.items():
        secrets = shingles(finder, policy, user)
        labels = hidden_labels(finder, policy, user)
        expert = Expert(finder)
        qs = rng.sample(qa, a.per_persona)
        stats = dict(r=0, correct=0, cited=0, x=0, named=0, neg=0, refused=0, gen=0, gen_ok=0)
        times = []

        def ask(q):
            expert.reset()
            t0 = time.perf_counter()
            r = expert.ask(user, q)
            times.append(time.perf_counter() - t0)
            check_prompts(r, q, policy, secrets, planted, labels)
            return r

        for item in qs:
            r = ask(item["question"])
            if policy.can_read(user, item["path"]):
                stats["r"] += 1
                stats["correct"] += squash(item["answer"]).lower() in squash(r.answer).lower()
                stats["cited"] += any(s[1] == item["path"] for s in r.sources)
            else:
                stats["x"] += 1
                stats["named"] += bool(r.denial) and r.denial.drive == policy.drive_of(item["path"])
        for item in rng.sample(negatives, 15):
            r = ask(item["question"])
            stats["neg"] += 1
            stats["refused"] += r.answer == NOTHING or "could not find" in r.answer.lower() or not r.sources
        for item in rng.sample(general, 15):
            r = ask(item["question"])
            stats["gen"] += 1
            stats["gen_ok"] += any(s[1].startswith(tuple(item["expected"])) for s in r.sources)
        n = lambda k: stats[k]
        div = lambda x, y: f"{x / y:.2f}" if y else "-"
        p95 = sorted(times)[int(len(times) * 0.95)]
        rows.append(f"| {name} | {n('r')} | {div(n('correct'), n('r'))} | {div(n('cited'), n('r'))} | {n('x')} | {div(n('named'), n('x'))} | "
                    f"{n('neg')} | {div(n('refused'), n('neg'))} | {n('gen')} | {div(n('gen_ok'), n('gen'))} | {statistics.mean(times):.1f} / {p95:.1f} |")
        print(rows[-1], flush=True)

    # follow-ups: superuser, so any failure is the rewrite and not permissions
    by_event = {}
    for item in qa:
        m = EVENT.search(item["question"])
        if m:
            by_event.setdefault(m.group(0), []).append(item)
    pairs = [(e, rng.sample(v, 2)) for e, v in sorted(by_event.items()) if len({i["key"] for i in v}) >= 2]
    pairs = [(e, [x, y]) for e, (x, y) in pairs if x["key"] != y["key"]][: a.pairs]
    expert, kept, correct = Expert(finder), 0, 0
    examples = []
    for event, (first, second) in pairs:
        expert.reset()
        expert.ask("superuser", first["question"])
        follow = "And " + second["question"][0].lower() + second["question"][1:].replace("the " + event, "that event").replace(event, "that event")
        r = expert.ask("superuser", follow)
        kept += event in r.query
        correct += squash(second["answer"]).lower() in squash(r.answer).lower()
        if len(examples) < 4:
            examples.append(f"- `{follow}` -> `{r.query}`")
    follow_up = (f"Follow-ups ({len(pairs)} pairs, superuser): rewrite keeps the event name {kept / len(pairs):.2f}, "
                 f"follow-up answered correctly {correct / len(pairs):.2f}.\n\nExamples:\n" + "\n".join(examples))
    text = ("# Domain expert benchmark\n\nHard assertions on every prompt sent to the model: no planted PII, no text that only "
            "unreadable files contain, no denial details, and every notice is exactly the fixed wording.\n\n"
            + "\n".join(rows) + "\n\n" + follow_up + "\n")
    Path(a.out).write_text(text, encoding="utf-8")
    print("\n" + follow_up)


if __name__ == "__main__":
    main()
