"""Turn the finder's sources into PII-stripped passages for the domain expert.

Question-path component: reads files, never writes the filemap or the index. For every source it
  1. re-checks permission and findability (defence in depth: the finder already did),
  2. reads the file's CURRENT content (in-file edits do not hide a file, and answers must reflect them),
  3. strips personal data, chunks the text and picks the chunks that best match the question,
  4. drops any passage that still looks like it holds personal data.
Sources that fail a check are skipped and listed in `Retriever.dropped` with the reason.
"""

import hashlib
from dataclasses import dataclass

import numpy as np

from kf import llm, profiles
from kf.extract import extract_text
from kf.indexer import chunk_text, embedding_input
from kf.pii import contains_pii, strip


@dataclass
class RetrieverConfig:
    per_source: int = 2  # passages per source
    max_chars: int = 6000  # total text across all passages (about 1500 tokens)
    select: str = "best"  # "best": chunks closest to the question; "head": first chunks (baseline for the benchmark)


@dataclass
class Passage:
    path: str
    drive: str
    drive_name: str
    created: str
    text: str
    score: float


class Retriever:
    def __init__(self, finder, config=None, embed_documents=None):
        self.finder, self.config = finder, config or RetrieverConfig(max_chars=profiles.current().excerpt_chars)
        model = finder.index.meta["model"] or None
        self._embed_documents = embed_documents or (lambda texts: llm.embed_documents(texts, model))
        self.dropped = []

    def retrieve(self, user, query, result):
        """Passages for result.sources, best source first. `dropped` lists (path, reason) for skipped sources."""
        self.dropped, passages, used = [], [], 0
        for source in result.sources:
            for p in self._passages(user, query, source) or ():
                if used + len(p.text) > self.config.max_chars:
                    break
                passages.append(p)
                used += len(p.text)
        return passages

    def _drop(self, path, reason):
        self.dropped.append((path, reason))

    def _passages(self, user, query, source):
        f, path = self.finder, source.path
        if not f.policy.can_read(user, path):
            return self._drop(path, "not readable")
        entry = f.live.get(path)
        if entry is None:
            return self._drop(path, "not findable")
        root = f.root.resolve()
        file = (f.root / path).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            return self._drop(path, "missing or outside the corpus")
        try:
            content_hash = hashlib.sha256(file.read_bytes()).hexdigest()
            chunks = chunk_text(strip(extract_text(file)))
        except Exception as exc:  # unreadable or corrupt file
            return self._drop(path, f"unreadable: {exc}")
        if not chunks:
            return self._drop(path, "no text")
        scores = self._scores(query, path, entry, chunks, content_hash)
        k = min(self.config.per_source, len(chunks))
        chosen = sorted(np.argsort(-scores)[:k]) if self.config.select == "best" else range(k)
        out = []
        for i in chosen:
            if contains_pii(chunks[i]):  # strip() should make this impossible; fail closed if it ever is not
                self._drop(path, "personal data left after stripping")
                continue
            out.append(Passage(path, source.drive, source.drive_name, source.created, chunks[i], float(scores[i])))
        return out

    def _scores(self, query, path, entry, chunks, content_hash):
        index = self.finder.index
        q = index.embed_query(query)
        rows = index.rows_of(path)
        if content_hash == entry["content_hash"] and [index.chunks[i]["text"] for i in rows] == chunks:
            vectors = index.vectors[rows]  # file unchanged since indexing: reuse the stored vectors
        else:
            vectors = np.asarray(self._embed_documents(
                [embedding_input(path, entry["description"], c, index.meta["context"]) for c in chunks]), dtype=np.float32)
            vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        return vectors @ q
