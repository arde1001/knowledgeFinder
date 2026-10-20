"""Generate the synthetic corpus: python -m kf.corpus.generate --out testdata [--seed 1] [--no-llm] [--profile low] [--workers 4]

Writes <out>/drive/** plus ground truth: users/drives/shares.yaml, qa.jsonl, pii.json, manifest.json.
Ground truth is exact because planted facts and PII are appended verbatim whenever the model leaves them out.
"""

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from kf import llm, profiles
from kf.corpus.render import render
from kf.corpus.spec import DRIVES, build_general, build_negatives, build_spec
from kf.extract import extract_text

KIND_LABEL = {
    "minutes": "minutes of a meeting", "plan": "event plan", "report": "short post-event report",
    "slides": "slide deck, written as four short separate sentences", "budget": "short note accompanying a budget spreadsheet",
    "note": "informal working notes", "handbook": "informative page", "newsletter": "member newsletter",
    "position": "description of an open volunteer position (duties, time commitment, how to apply)",
}


def _clean(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"[*#`]+", "", text)
    paras = [re.sub(r"^\s*(?:[-•]|\d+[.)])\s+", "", p.strip()) for p in re.split(r"\n\s*\n|\n", text)]
    return [p for p in paras if p]


def _prompt(spec):
    about = DRIVES[spec.drive][4]
    p = (f"You write internal documents for a fictional student association. Write the body of a {KIND_LABEL[spec.kind]} "
         f"for {about} about: {spec.topic}. Plain prose, 100-180 words, no headings, no markdown, no placeholders. "
         "Do not write any email addresses, phone numbers, street addresses or bank accounts.")
    if spec.facts:
        p += " Include these statements naturally, word for word: " + " ".join(f['sentence'] for f in spec.facts)
    return p


def _fallback(spec):
    return [f"This {KIND_LABEL[spec.kind]} covers {spec.topic}. The group reviewed progress, assigned follow-up tasks "
            "and agreed to report back at the next meeting."]


def _paragraphs(spec, use_llm, cache):
    if spec.kind in ("budget", "contacts") or not use_llm:
        paras = _fallback(spec) if spec.kind != "contacts" else []
    else:
        prompt = _prompt(spec)
        key = cache / hashlib.sha1(f"{llm.CHAT_MODEL}\n{prompt}".encode()).hexdigest()
        if key.exists():
            text = key.read_text(encoding="utf-8")
        else:
            seed = int(hashlib.sha1(spec.path.encode()).hexdigest()[:8], 16)
            text = llm.chat([{"role": "user", "content": prompt}], seed=seed, max_tokens=500)
            key.write_text(text, encoding="utf-8")
        paras = _clean(text) or _fallback(spec)
    flat = " ".join(paras)
    for fact in spec.facts:  # keep ground truth exact whatever the model wrote
        if fact["sentence"] not in flat:
            paras.append(fact["sentence"])
    return paras + spec.pii_lines


def build(out, seed=1, use_llm=True, workers=4, limit=None):
    out = Path(out)
    spec = build_spec(seed)
    cache = out / ".prose_cache"
    cache.mkdir(parents=True, exist_ok=True)
    files = spec.files[:limit] if limit else spec.files

    def work(f):
        render(f, _paragraphs(f, use_llm, cache), out / "drive")
        return f.path

    with ThreadPoolExecutor(workers) as pool:
        for i, path in enumerate(pool.map(work, files), 1):
            if i % 25 == 0 or i == len(files):
                print(f"{i}/{len(files)} {path}", file=sys.stderr, flush=True)

    dump = lambda name, data: (out / name).write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")
    dump("users.yaml", {"users": spec.users})
    dump("drives.yaml", {"drives": spec.drives})
    dump("shares.yaml", {"shares": spec.shares})
    (out / "drive_meta.json").write_text(json.dumps({f.path: {"created": f.created} for f in files}, indent=1), encoding="utf-8")
    (out / "qa.jsonl").write_text("".join(
        json.dumps({"question": x["question"], "answer": x["answer"], "path": f.path, "drive": f.drive, "key": x["key"],
                    "aligned": bool(f.event)}) + "\n"
        for f in files for x in f.facts), encoding="utf-8")
    (out / "negatives.jsonl").write_text("".join(json.dumps(x) + "\n" for x in build_negatives(seed)), encoding="utf-8")
    (out / "general.jsonl").write_text("".join(json.dumps(x) + "\n" for x in build_general(files, seed)), encoding="utf-8")
    (out / "pii.json").write_text(json.dumps([{**x, "path": f.path} for f in files for x in f.pii], indent=1), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(
        [{"path": f.path, "drive": f.drive, "kind": f.kind, "fmt": f.fmt, "topic": f.topic} for f in files], indent=1), encoding="utf-8")
    return files


def verify(out, files):
    """Re-extract every file and confirm planted facts and PII survived the format round trip."""
    squash = lambda s: re.sub(r"\s+", " ", s)
    bad = []
    for f in files:
        text = squash(extract_text(Path(out) / "drive" / f.path))
        for x in f.facts:
            if squash(x["answer"]) not in text:
                bad.append((f.path, "fact", x["answer"]))
        for x in f.pii:
            if squash(x["value"]) not in text:
                bad.append((f.path, "pii", x["value"]))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="testdata")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-llm", action="store_true", help="template prose instead of the local model (fast, for tests)")
    ap.add_argument("--workers", type=int, help="parallel model calls (default: the profile's)")
    ap.add_argument("--limit", type=int, help="only the first N files (smoke test)")
    profiles.add_argument(ap)
    a = ap.parse_args()
    p = profiles.activate(a.profile)
    files = build(a.out, a.seed, not a.no_llm, a.workers or p.workers, a.limit)
    bad = verify(a.out, files)
    print(f"{len(files)} files, {sum(len(f.facts) for f in files)} facts, {sum(len(f.pii) for f in files)} PII strings, "
          f"{len(bad)} verification failures")
    for b in bad[:20]:
        print("FAIL", *b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
