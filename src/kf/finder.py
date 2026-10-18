"""Find the readable files that answer a question, plus at most one drive the user may ask for access to.

    PYTHONPATH=src .venv/bin/python -m kf.finder --data testdata --user <id> "question"

Deterministic code only; no LLM runs here. Result holds readable sources and a drive-level denial (drive, name,
contact role and nothing else). Design: docs/finder-design.md.
"""

import argparse
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import yaml

from kf import filemap
from kf.indexer import Index
from kf.lexical import Bm25
from kf.perms import Policy

POOL = 10  # ranking depth kept per question; max_sources and K must not exceed it


@dataclass
class Config:
    max_sources: int = 5
    ratio: float = 0.9
    min_score: float = 0.0
    K: int = 5
    N: int = 2
    min_denial_score: float = 0.0
    lex_weight: float = 0.0  # weight of the BM25 keyword score added to the cosine similarity (0 = embeddings only)
    denial_mode: str = "cluster"  # "cluster": N of the top K files in one unreadable drive; "best": the best match is restricted
    margin: float = 0.0  # "best" mode: that drive's best file must beat every file in other drives by this much

    def __post_init__(self):
        if not (1 <= self.max_sources <= POOL and 1 <= self.K <= POOL and self.N >= 1 and self.lex_weight >= 0):
            raise ValueError(f"max_sources and K must be 1-{POOL}, N at least 1, lex_weight not negative")
        if self.denial_mode not in ("cluster", "best") or self.margin < 0:
            raise ValueError("denial_mode must be 'cluster' or 'best', margin not negative")

    @classmethod
    def load(cls, path):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown finder settings: {sorted(unknown)}")
        return cls(**data)


@dataclass
class Source:
    path: str
    drive: str
    drive_name: str
    created: str
    description: str
    score: float
    best_chunk: int


@dataclass
class Denial:
    drive: str
    drive_name: str
    contact_role: str


@dataclass
class Result:
    sources: list
    denial: Denial | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Raw:
    """Rankings before thresholds, so thresholds can be tuned without searching again."""

    readable: list  # [(path, score, chunk)] best first, readable files only
    overall: list  # [(path, score, readable)] best first, all live files


class Finder:
    def __init__(self, policy, fm, index, root, config=None):
        self.policy, self.fm, self.index, self.root = policy, fm, index, root
        self.config = config or Config()
        self.timing = {}
        self.refresh()

    def refresh(self):
        """Recompute which files are findable. Call after the filemap, files or permissions change.

        shortcut: computed once (about 30 us per file) and the readable set is cached per user; per-query
        recomputation or a per-user mask is the upgrade when the corpus grows (docs/plan.md, Later).
        """
        self.live = filemap.live_files(self.fm, self.policy, self.root)
        self._live_set = set(self.live)
        self._readable = {}
        self._bm25 = None

    def _lexical(self):
        if self._bm25 is None:
            self._bm25 = Bm25([f"{c['path']} {self.live.get(c['path'], {}).get('description', '')} {c['text']}"
                               for c in self.index.chunks])
        return self._bm25

    def _readable_set(self, user):
        if user not in self._readable:
            self._readable[user] = {p for p in self._live_set if self.policy.can_read(user, p)}
        return self._readable[user]

    def retrieve(self, user, query, lex_weight=None):
        if not self.policy.knows(user):
            raise ValueError(f"unknown user {user!r}")
        readable = self._readable_set(user)
        t0 = time.perf_counter()
        q = self.index.embed_query(query)
        t1 = time.perf_counter()
        weight = self.config.lex_weight if lex_weight is None else lex_weight
        bonus = weight * self._lexical().scores(query) if weight else None
        t2 = time.perf_counter()
        mine = self.index.rank_files(q, k=POOL, allowed=readable, bonus=bonus)
        overall = [(p, s, p in readable) for p, s, _ in self.index.rank_files(q, k=POOL, allowed=self._live_set, bonus=bonus)]
        self.timing = {"embed": t1 - t0, "lexical": t2 - t1, "rank": time.perf_counter() - t2}
        return Raw(mine, overall)

    def decide(self, raw, config=None):
        cfg = config or self.config
        sources = []
        if raw.readable:
            best = raw.readable[0][1]
            for path, score, chunk in raw.readable[: cfg.max_sources]:
                if score >= cfg.min_score and score >= cfg.ratio * best:
                    e, drive = self.live[path], self.policy.drive_of(path)
                    sources.append(Source(path, drive, self.policy.drive_name(drive), e["created"], e["description"],
                                          score, chunk))
        denial = self._best_denial(raw, cfg) if cfg.denial_mode == "best" else self._cluster_denial(raw, cfg)
        return Result(sources, denial)

    def _denial(self, drive):
        return Denial(drive, self.policy.drive_name(drive), self.policy.contact_role(drive))

    def _cluster_denial(self, raw, cfg):
        per_drive = {}
        for path, score, readable in raw.overall[: cfg.K]:
            if not readable and score >= cfg.min_denial_score:
                per_drive.setdefault(self.policy.drive_of(path), []).append(score)
        strong = {d: max(s) for d, s in per_drive.items() if len(s) >= cfg.N}
        return self._denial(max(strong, key=strong.get)) if strong else None

    def _best_denial(self, raw, cfg):
        """The best file overall is unreadable and its drive beats every other drive by `margin`: the answer likely lives there."""
        if not raw.overall:
            return None
        path, score, readable = raw.overall[0]
        drive = self.policy.drive_of(path)
        if readable or score < cfg.min_denial_score:
            return None
        elsewhere = next((s for p, s, _ in raw.overall if self.policy.drive_of(p) != drive), None)
        if elsewhere is not None and score - elsewhere < cfg.margin:
            return None
        return self._denial(drive)

    def find(self, user, query):
        return self.decide(self.retrieve(user, query))


def load_finder(data, config_path="finder.yaml"):
    data = Path(data)
    config = Config.load(config_path) if Path(config_path).exists() else Config()
    return Finder(Policy.load(data), filemap.load(data / "filemap.json"), Index.load(data / "index"), data / "drive", config)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--user", required=True)
    ap.add_argument("--data", default="testdata")
    ap.add_argument("--config", default="finder.yaml")
    a = ap.parse_args()
    finder = load_finder(a.data, a.config)
    r = finder.find(a.user, a.question)
    for s in r.sources:
        print(f"{s.score:.3f}  {s.path}  ({s.drive_name}, {s.created})\n       {s.description}")
    if not r.sources:
        print("nothing found")
    if r.denial:
        d = r.denial
        print(f"\nFile(s) inside Drive {d.drive_name} may match; you do not have permission. Ask: {d.contact_role}")


if __name__ == "__main__":
    main()
