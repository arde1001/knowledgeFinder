# Domain Expert (proof of concept)

A local question-answering assistant for a student organisation. Members ask questions in plain language and get answers
only from files **they** are allowed to read. It runs entirely on your own computer: a small language model served by
[Ollama](https://ollama.com), no cloud service, no data leaves the machine.

This is a proof of concept. It uses a **synthetic test association** (invented people, drives and documents) in place of
the real Google Drives. A folder of ordinary files stands in for the drives, and the access rules are plain settings.

## How it works

```
question ──> finder ──> retriever ──> domain expert ──> answer + sources (+ "ask X" notice)
             │           │             │
             │           │             └ local LLM sees only the question, the chat history, the user's own account
             │           │               (roles, drives) and personal-data-free excerpts
             │           └ re-checks permission, removes emails/phones/IBANs/addresses
             └ ranks only files the user may read; separately notices when the best match is in a drive they cannot open
admin side:  labeler (LLM describes every file and folder)  ->  indexer (embeds the labelled files)
```

Rules the code keeps (details in `CLAUDE.md`):

- Permissions are decided by ordinary code, never by the model, and checked before any file is read and again afterwards.
- The model never receives text from a file the user may not read.
- If the best match is in a drive the user cannot open, they are told **only** the drive's name and whom to ask. No file
  names, counts or snippets.
- Only files that an administrator has labelled and indexed can be found.

## Test association

Six drives with nested folders (up to four levels), 19 test people, three kinds of access:

| Role | Opens |
|---|---|
| `test.board` | every drive |
| `test.leader` | `01_Leaders`, `Archive`, `Members` and the drive of the leader's own committee (`Com: FLC` or `Com: AC`) |
| `test.committee_member` | `Members` only |

On top of that the data has individual shares: single files, whole subfolders shared with named people, one subfolder
shared with a role and one shared with everybody, so partial access can be tried.

## Install

You need Python 3.11+, [Ollama](https://ollama.com/download) and 4 to 10 GB of disk. The model size depends on the hardware
**profile**: `high` (default, NVIDIA with 10 GB+ VRAM or Apple Silicon with 24 GB+), `mid` or `low` (8 GB machines, Intel
Macs, computers without a usable GPU). Which one fits: [`docs/system-requirements.md`](docs/system-requirements.md).

```bash
ollama pull qwen3:8b            # high: answers and labels (about 5 GB); mid: qwen3:4b-instruct, low: qwen3:1.7b
ollama pull nomic-embed-text    # high, mid: search embeddings (about 0.3 GB); low: snowflake-arctic-embed:33m

# Linux / macOS
python3 -m venv .venv && source .venv/bin/activate
# Windows (PowerShell)
#   py -3 -m venv .venv ; .venv\Scripts\Activate.ps1 ; $env:PYTHONUTF8 = "1"

pip install -e ".[dev]"
python -m kf.doctor --no-measure  # on a new machine: checks this computer and suggests a profile
python -m pytest -q             # optional: all tests should pass (two are skipped without test data)
```

Once the models are pulled, `python -m kf.doctor` also times them on this machine. Pass `--profile low` (or `mid`) to any
command to use a lighter setup, and pull that profile's models. Every new terminal: activate the environment again, and run
commands from this folder.

## Run the demo

**Option A: download the prebuilt test data.** Download `kf-testdata.zip` from the Releases page of this repository
(release `testdata-v1`) and unzip it in the repository root. It creates `testdata/` with the files, the labels and both
indexes. Then start the web demo:

```bash
python -m kf.web --data testdata
```

**Option B: generate it yourself.** This is the only way to use real files (they are processed on your machine only):

```bash
python -m kf.corpus.generate --out testdata     # test files written by the model, about 15 minutes on a GPU
python -m kf.labeler --data testdata            # describes every file, about 3 minutes
python -m kf.indexer --data testdata            # embeds them, seconds
python -m kf.web --data testdata                # starts everything and opens the window
```

Add `--profile low` (or `mid`) to any of these commands on a lighter machine. The labels serve every profile, but each
profile needs its own index: run `python -m kf.indexer --data testdata --profile low` once for it.

`python -m kf.web` starts Ollama itself if it is not running, serves the page on `127.0.0.1` only, and opens a browser
window. **Ctrl+C in that shell (or closing the shell) stops the server and the Ollama it started.** Options: `--port`,
`--no-browser`, `--no-ollama`, `--profile`.

In the window, pick a test user on the left, ask a question, then switch user and ask the same thing. The left side
shows what that user can open and offers one test question per drive. Answers appear as they are written. The **Model**
selector in the sidebar switches the chat model (and the embedding model, when more than one has an index and tuned
thresholds).

Quick try without waiting for the model to write the files: add `--no-llm` to the generate command (plain template text,
seconds). The answers are then less natural.

More detail, including using a fragment of real files: [`docs/tutorial.md`](docs/tutorial.md).
Windows and macOS status: [`docs/windows-mac.md`](docs/windows-mac.md). Hardware and speed per profile:
[`docs/system-requirements.md`](docs/system-requirements.md).

## Other commands

```bash
python -m kf.workspace users --data testdata               # who exists and which drives each can open
python -m kf.expert --user lukas.gallagher --data testdata # the same assistant as a terminal chat (--debug shows the prompts)
python evals/run_suite.py --quick                          # tests, zero-leak check, accuracy; writes evals/suite_report.md
python evals/run_suite.py --quick --profile low            # the same checks with a profile
python evals/demo.py                                       # the same questions asked as six people
```

## Layout

| Path | What |
|---|---|
| `src/kf/` | the components: `perms`, `labeler`, `indexer`, `finder`, `retriever`, `expert`, `account`, `pii`, `web/` |
| `src/kf/corpus/` | generator of the synthetic association |
| `src/kf/workspace.py` | sets up a fragment of real files for testing |
| `tests/`, `evals/` | unit tests, benchmarks and the persona demo |
| `docs/` | `tutorial.md`, `windows-mac.md`, `system-requirements.md`, `plan.md` (decisions), `finder-design.md` |
| `profiles.yaml` | hardware profiles: models and work per step (`low`, `mid`, `high`) |
| `finder.yaml`, `finder-snowflake-arctic-embed_33m.yaml` | search thresholds per embedding model, tuned on the synthetic data |
| `testdata/` | generated, not in git |

## Limits

- Tuned on synthetic data. The thresholds in the `finder*.yaml` files need re-tuning on real documents.
- Personal-data removal is rule-based: it knows emails, phone numbers, digit-only IBANs and Finnish, Swedish and
  English-style street addresses. Other formats (for example IBANs with letters in the bank code, German or Spanish
  street addresses) can reach the model. **Use real files for local testing only.**
- The web page has no login: the test user is picked from a list. It listens only on the local machine and is a
  demonstration of the permission model, not a deployment.
- English only. No images or scanned PDFs.
- Windows and macOS: see `docs/windows-mac.md`.
