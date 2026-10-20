"""Admin tool: embed the findable files into a vector index. Never runs on the question path.

    PYTHONPATH=src .venv/bin/python -m kf.indexer --data testdata [--profile low] [--model nomic-embed-text] [--no-context]

Only files that are live in the filemap are indexed. Text is PII-stripped before chunking, so no chunk text or
vector is derived from personal data. By default each chunk is embedded together with its file name and the labeler's
description, which ranks the right file higher (evals/index_benchmark.md: nomic-embed-text hit@1 0.85 vs 0.80, MRR 0.895
vs 0.878; hit@5 about equal, slightly lower on cross-topic mentions). --no-context embeds the chunk text alone.

Index = vectors.npy (unit vectors, one row per chunk) + chunks.json ({"meta", "chunks": [{"path", "chunk", "text"}]}),
in <data>/index/<model>/ so indexes of several embedding models can sit side by side (index_dir).
"""

import argparse
import json
from functools import lru_cache
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from kf import filemap, llm, profiles
from kf.extract import extract_text
from kf.perms import Policy
from kf.pii import strip

CHUNK_CHARS = 900


def chunk_text(text, limit=CHUNK_CHARS):
    """Greedy paragraph packing up to `limit` characters; over-long paragraphs are split at sentences, then hard-cut."""
    pieces = []
    for para in filter(None, (p.strip() for p in re.split(r"\n+", text))):
        for sentence in re.split(r"(?<=[.!?]) +", para) if len(para) > limit else [para]:
            pieces += [sentence[i : i + limit] for i in range(0, len(sentence), limit)]
    chunks, cur = [], ""
    for piece in pieces:
        if cur and len(cur) + 1 + len(piece) > limit:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{piece}" if cur else piece
    return chunks + [cur] if cur else chunks


def embedding_input(path, description, text, context):
    return f"{path.rpartition('/')[2]}: {description}\n{text}" if context else text


def build_index(root, fm, policy, out, embed_documents=llm.embed_documents, model="", context=True):
    root, out = Path(root), Path(out)
    live = filemap.live_files(fm, policy, root)
    chunks, inputs = [], []
    for path, entry in sorted(live.items()):
        for i, text in enumerate(chunk_text(strip(extract_text(root / path)))):
            chunks.append({"path": path, "chunk": i, "text": text})
            inputs.append(embedding_input(path, entry["description"], text, context))
    vectors = np.asarray(embed_documents(inputs), dtype=np.float32).reshape(len(inputs), -1)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    meta = {"model": model, "context": context, "files": len(live), "built": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "vectors.npy", vectors)
    (out / "chunks.json").write_text(json.dumps({"meta": meta, "chunks": chunks}, ensure_ascii=False), encoding="utf-8")
    return meta


def same_model(a, b):
    return a.removesuffix(":latest") == b.removesuffix(":latest")


def index_dir(data, model):
    """<data>/index/<model>/. An older single index directly in <data>/index is used when it was built with this model."""
    base = Path(data) / "index"
    legacy = base / "chunks.json"
    if legacy.exists() and same_model(json.loads(legacy.read_text(encoding="utf-8"))["meta"]["model"], model):
        return base
    return base / profiles.slug(model)


class Index:
    def __init__(self, vectors, chunks, meta, embed_query=None):
        self.vectors, self.chunks, self.meta = vectors, chunks, meta
        self._rows = {}
        for i, c in enumerate(chunks):
            self._rows.setdefault(c["path"], []).append(i)
        self._embed_query = lru_cache(maxsize=256)(embed_query or (lambda text: llm.embed_query(text, meta["model"] or None)))

    @classmethod
    def load(cls, directory, embed_query=None):
        d = Path(directory)
        data = json.loads((d / "chunks.json").read_text(encoding="utf-8"))
        return cls(np.load(d / "vectors.npy"), data["chunks"], data["meta"], embed_query)

    def rows_of(self, path):
        """Row numbers of a file's chunks, in document order."""
        return self._rows.get(path, [])

    def embed_query(self, text):
        v = np.asarray(self._embed_query(text), dtype=np.float32)
        return v / max(float(np.linalg.norm(v)), 1e-12)

    def rank_files(self, query_vector, k=5, allowed=None, bonus=None):
        """Best files by their best chunk: [(path, score, chunk_no)]. `allowed` restricts the search to those paths;
        `bonus` is an extra score per chunk (e.g. weighted BM25) added to the cosine similarity."""
        scores = self.vectors @ query_vector
        if bonus is not None:
            scores = scores + bonus
        best = {}
        for i in np.argsort(-scores):
            c = self.chunks[i]
            if (allowed is None or c["path"] in allowed) and c["path"] not in best:
                best[c["path"]] = (c["path"], float(scores[i]), c["chunk"])
                if len(best) == k:
                    break
        return list(best.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="testdata")
    ap.add_argument("--model", help="embedding model (default: the profile's)")
    ap.add_argument("--no-context", action="store_true", help="embed chunk text alone, without the file label")
    ap.add_argument("--out", help="default: <data>/index/<model>")
    profiles.add_argument(ap)
    a = ap.parse_args()
    p = profiles.activate(a.profile)
    model = a.model or p.embed_model
    data = Path(a.data)
    out = Path(a.out) if a.out else index_dir(data, model)
    t0 = time.time()
    meta = build_index(
        data / "drive", filemap.load(data / "filemap.json"), Policy.load(data), out,
        embed_documents=lambda texts: llm.embed_documents(texts, model), model=model, context=not a.no_context,
    )
    print(f"{meta} in {time.time() - t0:.1f}s -> {out}")


if __name__ == "__main__":
    main()
