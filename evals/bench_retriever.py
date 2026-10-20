"""Retriever benchmark: does the context handed to the domain expert contain the planted answer, and no personal data?

    PYTHONPATH=src .venv/bin/python evals/bench_retriever.py [--out evals/retriever_benchmark.md]

For every persona and every question whose source file the persona can read: finder -> retriever, then check whether the
passages contain the planted answer. Hard assertions: no planted PII string in any passage, nothing dropped, every
passage readable by the persona. Settings compared: best-matching passages vs first chunks (baseline), 1 vs 2 per source.
"""

import argparse
import json
import re
import statistics
import time
from pathlib import Path

import bench_finder as bf
from kf.retriever import Retriever, RetrieverConfig

squash = lambda s: re.sub(r"\s+", " ", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "retriever_benchmark.md"))
    a = ap.parse_args()
    policy, finder, personas, users, _ = bf.load(bf.config())
    qa = bf.read_jsonl("qa.jsonl")
    planted = [squash(x["value"]) for x in json.loads((bf.DATA / "pii.json").read_text(encoding="utf-8"))]
    settings = [("best, 2 per source", RetrieverConfig(per_source=2, select="best")),
                ("best, 1 per source", RetrieverConfig(per_source=1, select="best")),
                ("head (first chunks), 2 per source", RetrieverConfig(per_source=2, select="head"))]
    lines = ["| persona | setting | readable q | source returned | answer in context | answer in context given the source was returned | chars of context (mean / p95) | retrieval ms (mean / p95) |",
             "|---|---|---|---|---|---|---|---|"]
    for name, user in personas.items():
        results = {}
        for i, item in enumerate(qa):
            if policy.can_read(user, item["path"]):
                results[i] = finder.find(user, item["question"])
        for label, cfg in settings:
            r = Retriever(finder, cfg)
            returned = hit = 0
            chars, times = [], []
            for i, res in results.items():
                item = qa[i]
                t0 = time.perf_counter()
                passages = r.retrieve(user, item["question"], res)
                times.append(time.perf_counter() - t0)
                assert not r.dropped, (name, r.dropped)
                text = squash(" ".join(p.text for p in passages))
                assert all(policy.can_read(user, p.path) for p in passages)
                assert not [v for v in planted if v in text], f"PII reached the context for {item['question']}"
                chars.append(len(text))
                returned += any(s.path == item["path"] for s in res.sources)
                hit += squash(item["answer"]) in text
            n = len(results)
            p95 = lambda xs: sorted(xs)[int(len(xs) * 0.95)]
            lines.append(f"| {name} | {label} | {n} | {returned / n:.3f} | {hit / n:.3f} | {hit / max(returned, 1):.3f} | "
                         f"{statistics.mean(chars):.0f} / {p95(chars)} | {statistics.mean(times) * 1000:.1f} / {p95(times) * 1000:.1f} |")
    text = "# Retriever benchmark\n\nzero planted PII strings in any context, nothing dropped (asserted).\n\n" + "\n".join(lines) + "\n"
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
