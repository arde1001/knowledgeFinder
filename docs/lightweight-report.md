# Lightweight branch: phase-by-phase report

Branch `lightweight` (from `main` at d3f621f), 2026-10-20. Goal: the proof of concept runs acceptably on laptops and
Macs without a strong GPU, while keeping everything mergeable into `main` later. **The default profile `high` behaves
exactly like `main`**: without `--profile` nothing changes for the development PC.

Nothing was pushed. The test-data release is prepared but not uploaded (see "Needs you").

## Summary

- **Hardware profiles** `low` / `mid` / `high` (`profiles.yaml`) on every command (`--profile` or `KF_PROFILE`).
- **On a 4-core CPU, an answer now takes 6 s on average with `low`**, against 32 s with today's default (75 s worst case).
  Labelling 249 files takes about 25 min instead of about 1 h 50 min. Building the index takes 18 s instead of 62 s.
- **Every profile passes every hard security check:**
  - zero leaks over every user × every question;
  - no PII in any prompt;
  - the notice never appears in a prompt;
  - no unanswerable question is ever answered.
- **Quality:**
  - `mid` matches `high`.
  - `low` is close on single questions but weak on follow-ups (details below).
- **Found a bug in `main`'s advice:** `qwen3:4b` in Ollama is a thinking-only model. It ignores `think: false` and writes
  its reasoning into answers and labels. It took 71 s per CPU answer, against 18 s for `qwen3:4b-instruct`. The README and
  tutorial on `main` still recommend it, so consider fixing that on `main` now, since your friends use it.

## Commits (each can be reverted on its own)

| Commit | Phase | What |
|---|---|---|
| 6a2b417 | 0 | `evals/bench_profile.py` (cost per step for model + device), baseline numbers |
| 3480e57 | 1 | profiles, per-model indexes, `tuned_for` guard, prompt budget guard |
| 7a285f0 | 2 | web warm-up, profile Ollama settings, extraction cache |
| 983cc60 | 4 | `kf.doctor` (Sonnet agent) |
| 35f7271 | 3 + 5 | `low` uses `snowflake-arctic-embed:33m` with tuned thresholds; `run_suite --profile`; `kf.workspace pack` |
| 88e6ec3 | 4 | streaming answers in the web demo (Sonnet agent) |
| 26f9444 | 4 | per-session model picker in the web demo (Sonnet agent) |
| afa3d20 | – | merge of the two web commits |
| last commit | 3 + 5 | benchmark reports, docs, this report |

**Rollback notes:**
- **Phase 1 is the base** the others build on. Revert the later commits first.
- **The web features** came in through a merge. Revert both with `git revert -m 1 afa3d20`, or only one with
  `git revert 26f9444` (picker) or `git revert 88e6ec3` (streaming).

---

## Phase 0: baseline

Built `evals/bench_profile.py`, which times every step for a given (chat model, embedding model, device). "cpu" forces
Ollama onto 4 threads of the i7-7700K (`num_gpu: 0`), a stand-in for a 4-core laptop or an Intel Mac.

Findings (`evals/profile_benchmark.md`):
- **Reading the prompt (prefill) is the cost on a CPU, not writing the answer.** Prompts are only about 750 tokens, yet
  `qwen3:8b` reads them at 39 tokens/s, which is 25 s before the first word.
- **Embedding on a CPU is about 20 times slower than on the GPU** (5 against 97 chunks/s for nomic-embed-text). That is
  one minute for the test data, but about an hour for 15,000 real chunks.
- **`qwen3:4b` is thinking-only in Ollama** (see the summary). `gemma3:4b` and `llama3.2:3b` accept `think: false`
  without an error on Ollama 0.33.3, so the planned capability check was not needed and was dropped.

## Phase 1: core plumbing

- **`profiles.yaml` and `src/kf/profiles.py`:**
  - One profile sets the chat model, embedding model, finder thresholds file, context size (`num_ctx`), workers, label
    input length, excerpt budget, answer length, history turns and Ollama server settings.
  - Precedence: `KF_CHAT_MODEL` / `KF_EMBED_MODEL` > `--profile` / `KF_PROFILE` > `high`.
  - A test pins `high` to the values `main` uses.
- **`llm.py`** reads the models and `num_ctx` from the profile. The hard-coded 8192 is gone; a smaller context means a
  smaller memory cache.
- **Indexes per embedding model** live in `<data>/index/<model>/`. An old index directly in `<data>/index/` is still
  used when it was built with the same model, so existing setups keep working.
- **Security guard (invariant 4).** The finder's score thresholds belong to one embedding model.
  - Each finder file now says `tuned_for:`, and the finder **refuses to start** with an index built by another model.
  - Before, a model swap would have silently broken the source cut-off and the denial notice.
- **Prompt budget guard.** Ollama silently cuts an overlong prompt *from the front*, which removes the system rules
  first. The expert now drops old turns, then the weakest excerpts, until the prompt fits the context.
- **Wiring:** every command takes `--profile`, and the eval scripts follow `KF_PROFILE`.
- **Tests:** profiles, `tuned_for` refusal, index location, prompt guard (2 tests).

## Phase 2: code optimizations

- **Warm-up.** The web demo loads both models and the keyword index at start, so the first question no longer waits
  2–20 s for loading. Measured: the first answer arrived in 0.4 s.
- **Ollama settings per profile.** When `kf.web` starts Ollama itself, low and mid use:
  - `OLLAMA_NUM_PARALLEL=1`
  - `OLLAMA_MAX_LOADED_MODELS=2` (stops the chat and embedding models from evicting each other)
  - `OLLAMA_FLASH_ATTENTION=1`
  - `OLLAMA_KV_CACHE_TYPE=q8_0` (about half the cache memory)

  These **do not apply to an Ollama that is already running** (e.g. the macOS app). `docs/windows-mac.md` explains how to
  set them there.
- **Extraction cache.** The retriever caches PII-stripped chunks by the file's content hash. Unchanged files are not
  parsed again, and an edited file still is (the "current content" rule holds; there is a test). Measured parsing costs
  only 5–10 ms per file on the test data, but real multi-page PDFs cost far more.
- **Skipped on purpose:** faster ranking (it measures 2 ms) and skipping the follow-up rewrite call. Neither is a
  measurable bottleneck.

## Phase 3: model candidates and tuning

**Embedding models** (`evals/index_benchmark_small.md`):

| | hit@1 | hit@5 | CPU chunks/s |
|---|---|---|---|
| nomic-embed-text (now) | 0.89 | 0.99 | 5.1 |
| **snowflake-arctic-embed:33m** | 0.87 | 0.98 | 18.6 |
| granite-embedding:30m | 0.66 | 0.93 | 31.3 |
| all-minilm | 0.74 | 0.98 | 30.8 |

`low` uses snowflake.
- **Thresholds.** It has its own tuned file `finder-snowflake-arctic-embed_33m.yaml`, made the same way as `finder.yaml`
  (lexical sweep, then denial sweep). Its scores run about 0.07 lower: `min_score` 0.80 against 0.87, with the same
  margin 0.04.
- **Notices.** The notice names the right drive for 84 % of restricted questions (nomic: 86 %), with zero wrong or extra
  notices.
- **Benchmark tooling.** The denial sweep in `bench_finder.py` is now relative to the config's `min_score`, so it works
  for any embedder.

**Chat models:** `low` = `qwen3:1.7b`, `mid` = `qwen3:4b-instruct`, `high` = `qwen3:8b`.
- `gemma3:4b` and `llama3.2:3b` were pulled but not benchmarked further: the qwen models already cover each tier.
- **Labelling** works with the small models: 50 out of 50 sample files got usable labels with both `qwen3:1.7b` and
  `qwen3:4b-instruct`, with sensible descriptions.
- **Corpus generation** works with `qwen3:1.7b`: 30 files, 0 verification failures.

**Quality** (full tables in `docs/system-requirements.md`; reports in `evals/suite-low/`, `evals/suite-mid/`,
`evals/cutoff_benchmark-*.md`):

| | high | mid | low |
|---|---|---|---|
| Answer correct | 0.96–1.00 | 0.96–1.00 | 0.93–1.00 |
| Unanswerable refused | 1.00 | 1.00 | 1.00 |
| Account questions (of 8) | 8 | 7 | 6 |
| Follow-up keeps the event / answered | 1.00 / 1.00 | 1.00 / 0.95 | **0.52 / 0.62** |

**Speed** (this PC; CPU = 4 threads of the i7-7700K):

| | Answer turn (CPU) | First word (CPU) | Label 249 files (CPU) | Chat model memory |
|---|---|---|---|---|
| high | 32 s | 25 s | ~1 h 50 min | 6.3–6.7 GB |
| mid | 17 s | 13 s | ~55 min | 3.6 GB |
| low | 6 s | 4 s | ~25 min | 1.7–1.9 GB |

On the GPU every profile answers in 0.4–0.5 s. Estimates for Macs and laptops are in `docs/system-requirements.md`.
They are labelled as estimates until a friend runs `kf.doctor`.

## Phase 4: extras (two Sonnet agents in parallel, then reviewed and merged)

- **`python -m kf.doctor [--profile NAME] [--no-measure]`:**
  - **Checks:** reports OS, CPU, RAM and GPU (NVIDIA, Apple Silicon or none), then Ollama and the pulled models.
  - **Timing:** times one prompt of about 1500 tokens and 32 embeddings.
  - **Warnings:** flags models evicting each other (a reload after an embed), a model spilling from the GPU to the CPU,
    and a too-slow profile.
  - **Output:** suggests a profile and prints a block to paste back. It prints no hostname, username or paths.
  - **Status:** 22 unit tests with a stubbed Ollama. Not yet run by hand on a real Mac or Windows machine.
- **Streaming answers.** `POST /api/ask_stream` sends the model's words as they come, then one final event.
  - The final event's answer *replaces* the streamed text: NOT_FOUND becomes the standard message, and dangling
    citations are removed.
  - Sources and the denial notice exist only in the final event, never in the stream (invariant 3).
  - The page falls back to `/api/ask` if streaming fails before the first word.
  - Verified against the real models with curl.
- **Model picker.** A "Model" card in the sidebar switches the chat model and the embedding model per browser session.
  - Chat models offered: those in `profiles.yaml` that Ollama has pulled.
  - Embedding models offered: only those with a built index *and* a finder file tuned for them, so it can never offer a
    pairing the finder would refuse.
  - Switching resets that session's history.
  - Verified with curl: a session switched to `qwen3:4b-instruct` + nomic answered correctly.

## Phase 5: bundle and docs

- **`python -m kf.workspace pack --data testdata`** zips a generated corpus with its labels and every index (4.3 MB).
  - It **refuses** any folder without the generator's `manifest.json`.
  - It also refuses when any file under `drive/` is not in that manifest, so real files can't be packed by mistake.
    There is a test.
- **Docs** (Haiku agent, checked and corrected):
  - README, tutorial and `docs/windows-mac.md` are in step. They cover profiles, the doctor, the Option A/B/C test data
    paths (prebuilt download, generate yourself, real files), per-model indexes, the Mac/Windows Ollama settings, and the
    `qwen3:4b` fix.
  - New `docs/system-requirements.md`: requirements per profile, measured speed, estimates for other machines, what makes
    it slow, and quality per profile.
  - New entry in `docs/plan.md`.
  - `CLAUDE.md` is updated for future sessions.
- **Generation stays fully supported.** Local generate → label → index works with every profile, and real data still
  goes only through the local `kf.workspace init` → labeler → indexer path.

---

## Needs you

1. **Upload the test-data release** (stopped here, as you asked: no `gh` push without you). The zip is at
   `/tmp/claude-1000/-home-arde1001-Projects-knowledgeFinder/c381639c-b708-4837-bb81-24d6a30d7771/scratchpad/kf-testdata.zip`,
   or rebuild it with `python -m kf.workspace pack --data testdata`.

   The docs refer to a release named `testdata-v1`:
   ```
   gh release create testdata-v1 kf-testdata.zip --title "Synthetic test data" --notes "Generated test corpus with labels and indexes for the high/mid (nomic) and low (snowflake) profiles. Unzip in the repository root."
   ```
   If the repository is private, your friends need access to download it. The docs' download step also assumes the
   branch is pushed, so they can use `--profile`.
2. **Click through the page once in a browser.** The streaming and the picker are covered by tests and were checked with
   curl, but the page itself wasn't opened: the automated browser had no Chrome installed. Run
   `python -m kf.web --data testdata --profile low`, ask a question, switch the model in the sidebar, then ask again.
3. **Ask a friend on each Mac** to run `python -m kf.doctor` and send the block back. Their numbers replace the
   estimates in `docs/system-requirements.md`.

## Open decisions

- **Follow-ups on `low`.** `qwen3:1.7b` keeps the event name in only 52 % of follow-up rewrites. Options:
  - (a) Leave it as is; the docs advise asking full questions on `low`.
  - (b) A code fallback: when the rewrite leaves "that event" / "it" unresolved, search with the previous question
    plus the follow-up.
  - (c) Run `low` with `qwen3:4b-instruct` and accept 17 s per CPU answer.

  I'd try (b). It's a small change, but it adds a heuristic to the question path, so it's your call.
- **What to merge into `main`.** Everything here is hardware-neutral and keeps `main`'s behaviour under `high`: profiles,
  per-model indexes and the `tuned_for` guard, the prompt guard, warm-up, extraction cache, doctor, streaming, picker,
  pack, and the `qwen3:4b` doc fix. Two things will diverge:
  - **Profile values:** a stronger PC or server may want its own profile (e.g. a bigger chat model). That is one more
    entry in `profiles.yaml`, plus a tuned finder file only if its embedding model differs.
  - **Benchmark reports:** they are per machine, so keep them per branch.

## Known limits

- The Mac and laptop speeds are estimates. The CPU stand-in is a desktop CPU and has no thermal throttling.
- The quality numbers come from the synthetic corpus and its 249 short files. Re-tune the thresholds on real files, as
  before.
- `profiles.yaml` and the finder files are found relative to the working directory (like `finder.yaml` before), so run
  the commands from the repository root.
