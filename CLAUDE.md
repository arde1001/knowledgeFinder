# CLAUDE.md

Guidance for Claude Code in this repository. The full plan and decision log is `docs/plan.md`; read it before starting a component.

## What this is

A local proof of concept for a student NGO: a RAG "domain expert" that answers member questions from a (test) file tree while enforcing the same access rules as the association's Google Drives. Google Drive is replaced by a folder of synthetic files under `testdata/`. Roles are plain config values, not a real group system. The LLM is a small quantized model served by Ollama on this machine (RTX 2080 Ti, 22 GB). Components are Python CLIs and test harnesses; a local web demo (`python -m kf.web`) sits on top of the expert.

**The association's real details are confidential. Use synthetic data only.** Never ask for, invent as real, or write real names, drives, documents or contact details into the repo.

## Pipeline

web demo (`kf.web`) or CLI → **finder** (labelled tree narrows, embeddings rank, permission-filtered) → **retriever** (PII-stripped chunks) → **domain expert** (local LLM, multi-turn). Admin side: **labeler** (writes the filemap) and **indexer** (embeds labelled files). Build order and per-component scope are in `docs/plan.md`.

## Security invariants (never weaken; add a test when touching them)

1. The LLM prompt contains only: system prompt, the user's question and chat history, PII-stripped chunks from files the user may read, and the user's own account block (`kf.account`: their roles, the drives they can open, drives with single shared files, and folder labels only where they can read every file below). Denial notices are added by code after the model answers and are never in the prompt.
2. Permissions are decided by deterministic code, never by the LLM. They are checked before any file content is read, and again in the retriever.
3. A denial notice is drive-level only: drive display name and its manually labelled contact role. No file names, counts, snippets or any other file data. At most one drive per question (the strongest).
4. A notice names a drive only when the best file overall (ranked over all labelled files, restricted ones included) is unreadable by the user, scores above `min_denial_score`, and its drive beats every file in other drives by `margin` (the answer likely lives in that one drive). Specific questions fire it; general ones do not. Settings are in `finder.yaml`, tuned on `evals/denial_benchmark.md`. Wording is identical for partial access. The older "N of the top K in one drive" rule remains available as `denial_mode: cluster`.
5. Chat history stores only final answers. Raw chunks never persist across turns. Permissions are re-evaluated every turn.
6. Only files listed and fully labelled in the filemap are findable. Unlabelled files on disk never reach the expert.
7. The labeler and indexer are admin commands. The question path never writes to them or runs them.
8. A folder label summarises every file below it, so show it to a user only if they can read every file under that folder. Otherwise give the LLM just the user's readable files with their own labels, with no ancestor folders or their labels.

## Decisions to remember

- Permission model mirrors typical Google Drive use: shared drives with member roles, folder inheritance, individual file/folder shares, and org-wide items. A user may hold several roles (union).
- Test association (`kf.corpus.spec`): six drives with nested folders: `01_Leaders`, `Archive`, `Members` (open to everyone), `Com: FLC`, `Com: AC` and `Board` (the on-disk folder names have no colon: `Com_FLC`, `Com_AC`). Three kinds of people with exactly one plain role each: `test.board` (member of every drive, so it reads every folder), `test.leader` (reads `01_Leaders`, `Archive`, `Members` and the own committee's drive, which names the leader in its `members.users`) and `test.committee_member` (reads only `Members`). Individual access comes from `shares.yaml`: subfolder shares to named people (some across committees), one role share, one org-wide folder and single-file grants. Names are EU-wide ASCII. Roles are plain config values in `users.yaml`/`drives.yaml`. Contact roles are in `drives.yaml`.
- Corpus formats: md/txt, PDF, docx/xlsx/pptx. No OCR.
- Retriever (`kf.retriever`, question path, read-only): for each finder source it re-checks `can_read` and findability, rejects paths outside the corpus (symlinks), reads the file's CURRENT content, strips PII, picks the best-matching 2 chunks per source (stored vectors if the file is unchanged since indexing, fresh embeddings if it was edited), caps the total at 6000 characters, and drops any passage where PII-shaped text survives. Skipped sources are listed in `Retriever.dropped`. Benchmark: `evals/bench_retriever.py`.
- Expert (`kf.expert`, question path): per turn, rewrite a follow-up into a standalone question (one LLM call, only with history; last 4 question/answer pairs, no excerpts), find, retrieve, then one answer call with the numbered excerpts. English only (the association's working language). The source list ([n] path, drive, created date; cited sources only) and the denial notice are added by code after the answer; the model never sees the denial. The model is always called, with the account block (roles, openable drives with labels, shared drives; folder labels for a drive the question names, only if the user can read everything under them) and the excerpts ("none found" if empty), so questions like "what is my role?" or "what is in the General folder?" are answered without documents. A nothing-found reply lists the drives searched. If the question explicitly names a drive the user cannot open ("the Finance folder"), the model is told its contents are unknown and the standard notice for that drive is added. `Answer.prompts` holds every prompt sent, for the leak tests. Chat: `python -m kf.expert --user <id> [--debug]`. If the model's reply contains NOT_FOUND (alone or after an explanation), code shows the standard "could not find" message with no sources. Benchmark: `evals/bench_expert.py` (asserts no PII, no unreadable-only text, no notice text in any prompt).
- Eval suite: `python evals/run_suite.py [--quick]` runs the unit tests and the four hard-assertion benchmarks (`bench_leaks.py`: every user x every question with no LLM, with a negative control; finder, retriever, expert) and writes `evals/suite_report.md`. `evals/demo.py` writes the persona transcript `evals/demo_transcript.md` (the same questions asked as six people: board, two leaders, committee members, a guest).
- Sources: the finder returns 1-5 readable files, not just the top hit (dynamic: weak results are dropped). Design in `docs/finder-design.md`; code `src/kf/finder.py` (+ `src/kf/lexical.py` BM25), thresholds `finder.yaml`, benchmark `evals/bench_finder.py` (asserts zero leaks; rerun after any change to the finder, index or permissions).
- Labeler output: `filemap.json` plus a human-readable `filemap.md`. A file label has created date, type, short description and the permissions that applied (drive members + covering shares) with their hash. Created dates come from `drive_meta.json` (stands in for Drive's createdTime).
- Findability (`filemap.live_files`): a file is findable only if its label is complete, it still exists at that path, and its permissions hash equals the current policy's. In-file edits do not matter. A moved file is a new, unlabelled path until an admin reruns the labeler; the same goes for a permission change (rerun keeps the description and refreshes the permissions).
- Label descriptions are rejected if they contain PII-shaped text (`kf.pii`), so nothing PII-like enters the filemap.
- PII stripping (`kf.pii.strip`) is rule-based: emails, phones, IBANs, street addresses and postcodes become `[email]`, `[phone]`, `[iban]`, `[address]`. It is applied to text before chunking and embedding, and will be applied again on the retrieval path.
- Index (`kf.indexer`): admin command; indexes only `filemap.live_files`; 900-char chunks of stripped text; `nomic-embed-text`, each chunk embedded with its file name and label (benchmarked: `evals/index_benchmark.md`; `--no-context` turns the label off). `Index.rank_files(query_vec, k, allowed)` returns best chunk per file; the finder must pass `allowed` for readable results and do the denial comparison in code.
- Models are config values: chat `qwen3:8b` (env `KF_CHAT_MODEL`), embeddings `nomic-embed-text` (env `KF_EMBED_MODEL`). Reruns of the labeler/indexer are needed after changing them.
- Work component by component and benchmark each one. Ask the user when a design is underdefined or a decision needs their input.

- Tutorial: `docs/tutorial.md` is the short how-to for colleagues (install, test data or a fragment of real files via `kf.workspace`, label, index, run as a user). **Update it whenever a command, option, file layout, role or the install steps change in a way a user would notice**, and keep `docs/windows-mac.md` (what still blocks Windows/macOS) in step.

## Layout

- `src/kf/`: package, one module per component.
- `tests/`: pytest. `testdata/`: generated synthetic corpus, users, drives (regenerable; keep out of git if large).
- `docs/plan.md`: plan and decisions.

## Running

- Use the project venv: `.venv/bin/python` (created with `--system-site-packages`; deps are listed in `pyproject.toml`). Tests: `.venv/bin/python -m pytest` from the repo root. CLIs: `PYTHONPATH=src .venv/bin/python -m kf.<module>`, or plain `python -m kf.<module>` once `pip install -e .` has been run (the tutorial's way).
- Ollama is installed; start it with `ollama serve` if it isn't running (`curl localhost:11434/api/version`). Pulled so far: `qwen3:8b` (~76 tok/s with `think: false` on this GPU).
- Web demo (`kf.web`): `python -m kf.web --data testdata` is the one-shell demo. Standard-library `http.server` on 127.0.0.1 only (Host header check, JSON-only POST, no file outside `static/` is served), one `Expert` per browser session and user, model calls behind one lock. It starts Ollama as a child process when none answers and stops it on exit; the page opens in a Chrome/Edge/Chromium `--app` window or the default browser. Styling follows `docs/Brand Guidelines 2023.pdf` (colours, Open Sans bundled under the OFL) but **the association's name and logo must not appear anywhere** until it is a production feature; the PDF itself is git-ignored for that reason. Login is a test-user dropdown (no password): never expose it beyond localhost. The API returns only answer, standalone query, notice and cited sources, never prompts or excerpts. Tests: `tests/test_web.py`. Update the README and tutorial if the options or the page change.
- README.md is the entry point (install, run, limits); `docs/tutorial.md` is the longer walk-through. Keep both and `docs/windows-mac.md` in step with the commands.
