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

You need Python 3.11+, [Ollama](https://ollama.com/download), about 10 GB of disk, and ideally a GPU (NVIDIA with 8 GB+ or
Apple Silicon). Without a GPU labelling takes hours: use a smaller model (`KF_CHAT_MODEL=qwen3:4b`) and a small data set.

```bash
ollama pull qwen3:8b            # answers and labels (about 5 GB)
ollama pull nomic-embed-text    # search embeddings (about 0.3 GB)

# Linux / macOS
python3 -m venv .venv && source .venv/bin/activate
# Windows (PowerShell)
#   py -3 -m venv .venv ; .venv\Scripts\Activate.ps1 ; $env:PYTHONUTF8 = "1"

pip install -e ".[dev]"
python -m pytest -q             # optional: all tests should pass (two are skipped without test data)
```

Every new terminal: activate the environment again, and run commands from this folder.

## Run the demo

```bash
python -m kf.corpus.generate --out testdata     # test files written by the model, about 15 minutes on a GPU
python -m kf.labeler --data testdata            # describes every file, about 3 minutes
python -m kf.indexer --data testdata            # embeds them, seconds
python -m kf.web --data testdata                # starts everything and opens the window
```

`python -m kf.web` is the only command you need after the first three steps. It starts Ollama itself if it is not
running, serves the page on `127.0.0.1` only, and opens a browser window. **Ctrl+C in that shell (or closing the shell)
stops the server and the Ollama it started.** Options: `--port`, `--no-browser`, `--no-ollama`.

In the window, pick a test user on the left, ask a question, then switch user and ask the same thing. The left side
shows what that user can open and offers one test question per drive.

Quick try without waiting for the model to write the files: add `--no-llm` to the generate command (plain template text,
seconds). The answers are then less natural.

More detail, including using a fragment of real files: [`docs/tutorial.md`](docs/tutorial.md).
Windows and macOS status: [`docs/windows-mac.md`](docs/windows-mac.md).

## Other commands

```bash
python -m kf.workspace users --data testdata               # who exists and which drives each can open
python -m kf.expert --user lukas.gallagher --data testdata # the same assistant as a terminal chat (--debug shows the prompts)
python evals/run_suite.py --quick                          # tests, zero-leak check, accuracy; writes evals/suite_report.md
python evals/demo.py                                       # the same questions asked as six people
```

## Layout

| Path | What |
|---|---|
| `src/kf/` | the components: `perms`, `labeler`, `indexer`, `finder`, `retriever`, `expert`, `account`, `pii`, `web/` |
| `src/kf/corpus/` | generator of the synthetic association |
| `src/kf/workspace.py` | sets up a fragment of real files for testing |
| `tests/`, `evals/` | unit tests, benchmarks and the persona demo |
| `docs/` | `tutorial.md`, `windows-mac.md`, `plan.md` (decisions), `finder-design.md` |
| `finder.yaml` | search thresholds, tuned on the synthetic data |
| `testdata/` | generated, not in git |

## Limits

- Tuned on synthetic data. Thresholds in `finder.yaml` need re-tuning on real documents.
- Personal-data removal is rule-based: it knows emails, phone numbers, digit-only IBANs and Finnish, Swedish and
  English-style street addresses. Other formats (for example IBANs with letters in the bank code, German or Spanish
  street addresses) can reach the model. **Use real files for local testing only.**
- The web page has no login: the test user is picked from a list. It listens only on the local machine and is a
  demonstration of the permission model, not a deployment.
- English only. No images or scanned PDFs.
- Windows and macOS: see `docs/windows-mac.md`.
