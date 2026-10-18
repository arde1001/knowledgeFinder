"""BM25 keyword scoring over chunks, as a second signal next to the embeddings (exact names, codes, dates).

Scores are divided by the best score this query could reach, so 0 means no query term matched and values near 1
mean every term is present. A query term that occurs nowhere in the corpus (an invented event name) lowers every score.

shortcut: built in memory from the chunks at start-up, which is fine for hundreds of thousands of chunks; use an
inverted index persisted by the indexer (or the vector store's own full-text search) beyond that.
"""

import math
import re
from collections import Counter, defaultdict

import numpy as np

STOP = {"a", "an", "the", "is", "are", "was", "were", "be", "of", "for", "to", "in", "at", "on", "by", "with", "as",
        "and", "or", "what", "who", "how", "did", "does", "do", "which", "when", "where"}


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


class Bm25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.k1, self.b, self.n = k1, b, len(docs)
        lengths, postings = [], defaultdict(lambda: ([], []))
        for i, doc in enumerate(docs):
            tokens = tokenize(doc)
            lengths.append(len(tokens))
            for term, count in Counter(tokens).items():
                postings[term][0].append(i)
                postings[term][1].append(count)
        self.post = {t: (np.array(ids), np.array(tf, dtype=np.float32)) for t, (ids, tf) in postings.items()}
        self.len = np.array(lengths, dtype=np.float32)
        self.avg = max(float(self.len.mean()), 1.0) if self.n else 1.0

    def idf(self, term):
        df = len(self.post[term][0]) if term in self.post else 0
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def scores(self, query):
        """One normalised score per document."""
        out = np.zeros(self.n, dtype=np.float32)
        best = 0.0
        for term in set(tokenize(query)):
            weight = self.idf(term)
            best += weight * (self.k1 + 1)
            if term in self.post:
                ids, tf = self.post[term]
                norm = self.k1 * (1 - self.b + self.b * self.len[ids] / self.avg)
                out[ids] += weight * tf * (self.k1 + 1) / (tf + norm)
        return out / best if best else out
