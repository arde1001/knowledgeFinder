"""How loose can the finder's score cutoff (`min_score`) be before the expert answers things it should not?

    PYTHONPATH=src:evals .venv/bin/python evals/bench_cutoff.py [--values 0.87,0.8,...] [--out evals/cutoff_benchmark.md]

Real model. For each cutoff and two people (the superuser and a committee member), the expert is asked:
  - 45 casual paraphrases of corpus questions (written once by the local model, kept in testdata/paraphrases.jsonl),
    for the ones the person can read: answered correctly?
  - 35 unanswerable questions: ANY answer other than "could not find" is a wrong answer (the number that must stay 0);
  - 8 account questions (roles, drives, folder contents), for the committee member.
Only `min_score` changes; `ratio`, `min_denial_score` and the margin stay as in finder.yaml.
"""

import argparse
import json
import random
import re
import statistics
from dataclasses import replace
from pathlib import Path

import bench_finder as bf
from kf import llm
from kf.expert import NOTHING, Expert
from kf.finder import Config

squash = lambda s: re.sub(r"\s+", " ", s).strip().lower()
EVENT = re.compile(r"(?:[A-Z][a-z]+ )+20\d\d")
PARAPHRASE = """Rewrite this question the way a busy student would type it in a chat: short, casual, maybe lowercase, no formal wording.
Keep the event name and the year exactly. Output only the question.

Question: {q}"""


def paraphrases(qa, n=45):
    path = bf.DATA / "paraphrases.jsonl"
    if path.exists():  # reuse only while every cached question and answer is still in the corpus
        cached, current = bf.read_jsonl("paraphrases.jsonl"), {(q["question"], q["answer"]) for q in qa}
        if all((c["original"], c["answer"]) in current for c in cached):
            return cached
    rng, out = random.Random(1), []
    for item in rng.sample(qa, len(qa)):
        m = EVENT.search(item["question"])
        text = llm.chat([{"role": "user", "content": PARAPHRASE.format(q=item["question"])}], temperature=0.3, seed=1, max_tokens=60)
        text = text.splitlines()[0].strip().strip('"') if text else ""
        if m and m.group(0).lower() in text.lower() and text.lower() != item["question"].lower():
            out.append({**item, "original": item["question"], "question": text})
        if len(out) == n:
            break
    path.write_text("\n".join(json.dumps(x) for x in out) + "\n", encoding="utf-8")
    return out


def account_checks(policy, user):
    """(question, predicate on the reply) pairs; the predicates look for facts from the permission system and the filemap."""
    names = [policy.drive_name(d) for d in sorted(policy.drives_with_access(user))]
    roles = policy.roles_of(user)
    return [("What is my role?", lambda t: all(r in t for r in roles)),
            ("Which roles do I have?", lambda t: all(r in t for r in roles)),
            ("What drives do I have access to?", lambda t: all(n.lower() in t for n in names)),
            ("Which folders can I open?", lambda t: all(n.lower() in t for n in names)),
            ("What is in the Members folder?", lambda t: "newsletter" in t and "position" in t),
            ("What kind of things are in the Members drive?", lambda t: "newsletter" in t or "event" in t),
            ("What is in the Board folder?", lambda t: not any(w in t for w in ("budget", "minutes", "strategy", "audit", "hr "))),  # not openable: must not describe it
            ("Do I have access to the Board drive?", lambda t: "board" in t and not t.startswith("i could not"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--values", default="0.87,0.8,0.72,0.65,0.55")
    ap.add_argument("--out", default=str(Path(__file__).parent / "cutoff_benchmark.md"))
    a = ap.parse_args()
    base = Config.load("finder.yaml")
    policy, finder, personas, users, _ = bf.load(base)
    qa, negatives = bf.read_jsonl("qa.jsonl"), bf.read_jsonl("negatives.jsonl")
    para = paraphrases(qa)
    people = [("superuser", "superuser"), ("committee member", personas["member"])]
    rng = random.Random(0)
    originals = rng.sample(qa, 40)
    expert = Expert(finder)
    rows = ["| min_score | person | paraphrases answered correctly | standard questions answered correctly | unanswerable answered (must be 0) | account questions answered |", "|---|---|---|---|---|---|"]
    wrong_examples = []
    for value in [float(v) for v in a.values.split(",")]:
        finder.config = replace(base, min_score=value)
        for label, user in people:
            def ask(q):
                expert.reset()
                return expert.ask(user, q)
            def correct(items):
                rel = [i for i in items if policy.can_read(user, i["path"])]
                return sum(squash(i["answer"]) in squash(ask(i["question"]).answer) for i in rel), len(rel)
            pc, pn = correct(para)
            oc, on = correct(originals)
            wrong = [n["question"] for n in negatives if ask(n["question"]).answer != NOTHING]
            wrong_examples += [(value, label, q) for q in wrong[:2]]
            acc = account_checks(policy, user) if label != "superuser" else []
            ac = sum(check(squash(ask(q).answer)) for q, check in acc)
            rows.append(f"| {value} | {label} | {pc}/{pn} = {pc / pn:.2f} | {oc}/{on} = {oc / on:.2f} | {len(wrong)}/{len(negatives)} | "
                        + (f"{ac}/{len(acc)}" if acc else "-") + " |")
            print(rows[-1], flush=True)
    text = "# Cutoff (`min_score`) benchmark\n\n" + "\n".join(rows) + "\n"
    if wrong_examples:
        text += "\nExamples of unanswerable questions that got an answer:\n" + "\n".join(f"- {v} / {l}: {q}" for v, l, q in wrong_examples) + "\n"
    Path(a.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
