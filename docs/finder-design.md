# Finder design

The finder turns (user, query) into a short list of readable files plus, at most, one drive-level denial notice. It is deterministic code: no LLM runs inside it in this phase. The domain expert and retriever consume its output; they never see anything else about the corpus.

## Contract

```
find(user, query) -> Result
  sources: list[Source]   # 0-5 readable files, best first
  denial:  Denial | None  # at most one drive

Source = path, drive, drive_name, created, description, score, best_chunk
Denial = drive, drive_name, contact_role      # these three fields only
```

- `query` is already a standalone question (multi-turn rewriting happens in the domain expert).
- Every source passes `Policy.can_read(user, path)` and is a live file (`filemap.live_files`: complete label, same path, same permissions hash).
- Scores of unreadable files never leave the finder. A denial carries no file name, count, snippet or score.
- Empty `sources` means "nothing found". The expert must then say so rather than guess.

## Pipeline (baseline)

1. Embed the query with the index's model (`Index.embed_query`).
2. One global ranking over all live files, best chunk per file (`Index.rank_files(q, k=M, allowed=live)`, M about 50). Restricted files take part in this ranking: the denial rule needs them.
3. Split the ranking by `can_read(user, path)` into readable R and unreadable X.
4. **Sources.** Take R in score order, at most `max_sources` (5). Keep a file only if `score >= min_score` and `score >= ratio * best_readable_score`. A confident question therefore returns 1-2 files, a vague one up to 5.
5. **Denial.** Take the global top `K` (5) files. Among the unreadable ones, group by drive. A drive qualifies when at least `N` (2) of those files score at least `min_denial_score`. If several qualify, return the one with the highest best score. Individually shared files do not change this: the unreadable files of a partly accessible drive still count, and the notice wording is identical.
6. Return `Result`.

All thresholds live in `finder.yaml` (`max_sources`, `ratio`, `min_score`, `K`, `N`, `min_denial_score`) and are tuned on the eval set, not guessed. Tuned values are in `finder.yaml` (see `evals/finder_benchmark.md`); they must be re-tuned on real documents, because the score distributions will differ.

## Eval harness (`evals/bench_finder.py`)

Personas (built from the test corpus; the superuser exists only in the eval):
- **superuser**: reads every drive (the main case: the hardest search space, where permissions help nothing)
- **member**: one team plus general
- **dual**: two teams plus general
- **sharee**: one team plus individually shared files from other drives
- **general-only**: no team role

Per persona and question:
- **Leaks (hard assertion, zero tolerance):** every source is readable and live; the denial has only its three fields.
- **Ranking, for questions whose source file the persona can read:** hit@1/3/5, MRR, and the headline number, files opened before the right one.
- **Denials, for questions whose source file the persona cannot read:** recall (the notice names the source's drive) and spurious-notice rate (a notice for any other drive, or one when the source is readable).
- **Unanswerable questions (about 30 new ones, about events and people not in the corpus):** `sources` must be empty.
- **Latency per stage:** embed, rank, split, total.

The corpus's `aligned` tag splits all ranking numbers into aligned and cross-topic questions.

## Experiments after the baseline (each benchmarked against it, kept only if it helps)

1. **Label narrowing:** embed folder and drive labels, search chunks only inside the best folders. Expected to matter at scale, and it can lose recall if the right folder is missed. Must never consult labels the user cannot see (invariant 8).
2. **BM25 keyword signal** blended with the embedding score, for exact names and codes.
3. **Recency preference** from the label's created date, as a tie-breaker between near-equal scores.
4. **Query filters** for drive, team, event and year parsed from the query.

An LLM tree-walk is out of scope for the demo.

## Baseline results (synthetic corpus, 5 personas, 205 questions, zero leaks)

- Superuser: right file found 0.95 (aligned 0.97, cross-topic 0.85), hit@1 0.85, 0.19 wrong files opened before the right one, 2.45 sources per question. Restricted personas find 0.93-1.00 of the questions they can answer.
- Off-topic questions return nothing (min_score 0.70 vs a maximum of 0.59). Questions about invented events return nothing only 32-88% of the time: a dense embedding cannot tell "Lantern Night" from "Culture Night" inside the same question template. A keyword signal should help.
- Denial notice (K=3, N=2, min 0.70): when the answer is restricted, the notice names its drive 20% of the time and another drive 7-8%; 7-14% of readable questions and 11-17% of unanswerable ones also get a notice. Cause: topic similarity, not answer presence. Every team holds plans, budgets and slides for the same events, so a drive qualifies on topic, and the answer's own drive often has only one file in the top three. More recall is available (K=5: recall 0.30 but 0.23 extra notices) at the price of more noise.
- Latency: query embedding 20 ms, ranking 2 ms (12 ms p95).

## Experiment 1: BM25 keyword signal (adopted, `lex_weight: 0.3`)

Chunk text plus file path and label are scored with BM25 (`kf.lexical`), normalised to 0-1 (0 = no query term present; terms found nowhere in the corpus lower every score), weighted and added to the cosine similarity. Sweep in `evals/lexical_benchmark.md`; thresholds re-derived per weight. Superuser, weight 0 -> 0.3:

- right file in the top 5: 0.953 -> 0.994; hit@1: 0.847 -> 0.894; MRR 0.891 -> 0.939; wrong files opened before the right one: 0.19 -> 0.15; sources per question: 2.45 -> 1.46.
- questions about invented events returning nothing: 0.32 -> 1.00 (off-topic stayed at 1.00); notices on unanswerable questions: 0.14 -> 0.00.
- cost: 45 ms to build the BM25 index at start-up (715 chunks), 0.04 ms per query. No gain beyond weight 0.3.

Open caution: the score thresholds are set just below the weakest real question's top score, which is a single-point estimate on 170 synthetic questions; expect to re-tune them on real data.

## Experiment 2: denial rule "best match is restricted" (`denial_mode: best`, margin 0.04, adopted 2026-10-18)

New mode in the finder: a notice names a drive when the best file overall is unreadable, scores at least `min_denial_score`, and its drive beats every file in other drives by `margin` (the information then likely lives in that one drive). Eval additions: 24 general-information questions (`testdata/general.jsonl`: 12 association-level, 12 event overviews, where every team also holds related restricted files) and `evals/bench_finder.py --denial` (results in `evals/denial_benchmark.md`). Pooled over the four restricted personas, min score 0.87:

| rule | names the answer's drive | names another drive | notice though the answer is readable | notice on unanswerable | notice on general (of 96) |
|---|---|---|---|---|---|
| cluster K=3, N=2 (previous rule) | 0.14 | 0.04 | 0.05 | 0.00 | 0 |
| best, margin 0 | 0.92 | 0.06 | 0.09 | 0.00 | 17 (event overviews: 0.38) |
| best, margin 0.03 | 0.82 | 0.02 | 0.03 | 0.00 | 6 |
| **best, margin 0.04** | **0.76** | **0.01** | **0.03** | **0.00** | **0** |
| best, margin 0.05 | 0.72 | 0.00 | 0.03 | 0.00 | 0 |
| best, margin 0.06 | 0.62 | 0.00 | 0.00 | 0.00 | 0 |

The margin is what separates specific from general questions: event overviews have several similar files across drives, so no drive stands out. Proposed setting: `denial_mode: best`, `margin: 0.04`, `min_denial_score: 0.87`. Caveats: only 48 general questions per kind (4 personas x 12), margin values are on the combined cosine + 0.3 x BM25 scale, and the synthetic corpus has more look-alike files than the real drives will. Adopted with the project owner's approval; it replaces the earlier "N of the top K in one drive" rule (still available as `denial_mode: cluster`). To be re-tuned for production.

## Implementation plan

- `src/kf/finder.py`: `Finder(policy, filemap, index, root, config).find(user, query)`; `finder.yaml` defaults.
- `tests/test_finder.py` with a fake index and embedder: readable/unreadable split, dynamic source cut, denial rule (N of K, one drive, strongest wins, partial access, no leak of fields), empty result.
- `evals/bench_finder.py` as above; results go to `evals/finder_benchmark.md`.
- Tune the config on the benchmark, then run the experiments one at a time.
