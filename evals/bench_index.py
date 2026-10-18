"""Embedding benchmark: build an index per (model, context) and score retrieval on testdata/qa.jsonl.

    PYTHONPATH=src .venv/bin/python evals/bench_index.py [--models a,b,c] [--tmp DIR]

A question counts as a hit when its source file is among the top-k files (searched over all findable files,
no permission filter: this measures retrieval quality, not access control).
"""

import argparse
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from kf import filemap, llm
from kf.indexer import Index, build_index
from kf.perms import Policy

DATA = Path("testdata")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="nomic-embed-text,bge-m3,qwen3-embedding:0.6b")
    ap.add_argument("--tmp", default=None)
    a = ap.parse_args()
    qa = [json.loads(l) for l in (DATA / "qa.jsonl").read_text(encoding="utf-8").splitlines()]
    fm, policy = filemap.load(DATA / "filemap.json"), Policy.load(DATA)
    tmp = Path(a.tmp or tempfile.mkdtemp())
    rows = []
    for model in a.models.split(","):
        for context in (True, False):
            out = tmp / f"{model.replace(':', '_')}-{'ctx' if context else 'noctx'}"
            t0 = time.time()
            meta = build_index(DATA / "drive", fm, policy, out, lambda t: llm.embed_documents(t, model), model, context)
            build_s = time.time() - t0
            index = Index.load(out)
            t0 = time.time()
            qvecs = [index.embed_query(q["question"]) for q in qa]
            query_ms = (time.time() - t0) / len(qa) * 1000
            ranks = []
            for q, v in zip(qa, qvecs):
                paths = [p for p, _, _ in index.rank_files(v, k=10)]
                ranks.append(paths.index(q["path"]) + 1 if q["path"] in paths else None)
            hit = lambda k: sum(r is not None and r <= k for r in ranks) / len(qa)
            mrr = float(np.mean([1 / r if r else 0 for r in ranks]))
            split = lambda al: np.mean([bool(r and r <= 5) for r, q in zip(ranks, qa) if q["aligned"] == al])
            rows.append((model, context, len(index.chunks), build_s, query_ms, hit(1), hit(3), hit(5), mrr, split(True), split(False)))
            print(rows[-1], flush=True)
    lines = ["| model | label context | chunks | build s | query ms | hit@1 | hit@3 | hit@5 | MRR@10 | hit@5 aligned | hit@5 cross-topic |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {m} | {'yes' if c else 'no'} | {n} | {b:.1f} | {q:.0f} | {h1:.2f} | {h3:.2f} | {h5:.2f} | {mrr:.3f} | {a:.2f} | {x:.2f} |"
              for m, c, n, b, q, h1, h3, h5, mrr, a, x in rows]
    print("\n".join(lines))
    (Path(__file__).parent / "index_benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
