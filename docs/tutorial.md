# Tutorial: try the domain expert

Ask questions about the association and get answers only from files the chosen test user may read. Allow about 30 minutes, most of it waiting for the model. This is a proof of concept: use the generated test data, or a fragment of real files you are allowed to copy.

> Maintainers: update this page, `README.md` and `windows-mac.md` whenever a command, option, file layout, role or install step changes.

## 1. Install (once)

You need Python 3.11+, [Ollama](https://ollama.com/download) and 4 to 10 GB of disk, depending on the hardware profile (step 3). Labelling on a CPU is slow with the `high` profile: pick the profile that fits your machine.

1. Open a terminal in the project folder and create the environment.
   ```
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell). If activation is blocked: Set-ExecutionPolicy -Scope Process Bypass
   py -3 -m venv .venv
   .venv\Scripts\Activate.ps1
   $env:PYTHONUTF8 = "1"
   ```
2. Install the project, then check it. Do not skip the install: without it every `python -m kf...` command fails with `No module named 'kf'`.
   ```
   pip install -e ".[dev]"
   python -c "import kf; print(kf.__file__)"      # prints a path ending in src/kf/__init__.py
   python -m pytest -q                            # all tests pass (two are skipped until test data exists)
   ```
3. Choose a profile. Check the machine first; this needs no models:
   ```
   python -m kf.doctor --no-measure
   ```
   It prints the hardware and suggests a profile. Each profile sets the models and the amount of work per step (`profiles.yaml`); requirements and speeds are in [`system-requirements.md`](system-requirements.md).

   | Profile | Chat model | Embedding model | Typical machine |
   |---|---|---|---|
   | `high` (default) | `qwen3:8b` | `nomic-embed-text` | NVIDIA with 10 GB+ VRAM, Apple Silicon with 24 GB+ |
   | `mid` | `qwen3:4b-instruct` | `nomic-embed-text` | Apple Silicon with 16 GB, NVIDIA with 6-8 GB VRAM |
   | `low` | `qwen3:1.7b` | `snowflake-arctic-embed:33m` | 8 GB RAM, Intel Mac, no usable GPU |

   Every command below takes `--profile low` (or `mid`, `high`); it is optional, and `KF_PROFILE=low` does the same. Each profile needs its own index (step 4).
4. Download the two models of your profile (about 5.5 GB for `high`). Ollama must be running for this: the desktop app starts it; on Linux run `ollama serve` in another terminal.
   ```
   ollama pull qwen3:8b            # high
   ollama pull nomic-embed-text    # high
   ```
   For `mid` pull `qwen3:4b-instruct` and `nomic-embed-text`; for `low` pull `qwen3:1.7b` and `snowflake-arctic-embed:33m`. Then run `python -m kf.doctor` (without `--no-measure`) to time the models on this machine; it warns when they are too slow or run partly on the CPU.

Every new terminal: activate the environment again (and set `PYTHONUTF8` on Windows). Run all commands from the project folder.

## 2. Get data: A, B or C

Every later command takes `--data <folder>`.

**A. Download the prebuilt test data** (synthetic, safe to share; the quickest start). Download `kf-testdata.zip` from the Releases page of this repository (release `testdata-v1`) and unzip it in the project folder. It creates `testdata/` with the files, the labels and both indexes, so skip to step 5.

**B. Generate the test association yourself** (synthetic, safe to share): 249 files in 6 drives (`01_Leaders`, `Archive`, `Members`, `Com: FLC`, `Com: AC`, `Board`), folders up to four levels deep, 19 people.
```
python -m kf.corpus.generate --out testdata [--profile low]
```
(`--profile` is optional.) The model writes every file: about 15 minutes on a GPU. For a first run in seconds add `--no-llm` (plain template text: enough to try the steps, but answers read less naturally). Use a new or empty `--out` folder when you generate again. Then continue with the labeler (step 3) and the indexer (step 4).

**C. A fragment of real files**, downloaded as ordinary folders (not through Google Drive).
1. Put each shared drive's folder under `mydata/drive/`, for example `mydata/drive/Com_FLC/events/gala.docx`. The top-level folders are the drives (avoid `:` in folder names: Windows cannot store it). Supported files: md, txt, pdf, docx, xlsx, pptx. Keep real files out of git and share nothing you may not share. Personal-data removal only knows emails, phone numbers, IBANs written as digits and Finnish/Swedish/English-style street addresses: other address formats and bank codes with letters can reach the model, so use real files for local testing only.
2. Create the test setup (drives, invented test people, no individual shares, creation dates from file times):
   ```
   python -m kf.workspace init --data mydata
   ```
3. Open `mydata/drives.yaml` and set each drive's `contact_role` (the person named in "Ask: ..." notices). Edit `users.yaml` and `shares.yaml` if you want real people or individual shares. How `init` assigns access: a folder named `Members` (or `General`) is open to everyone; `Archive` and anything with `Leaders` in its name opens for leaders and board; `Board` for the board; every other folder is a committee drive that the board and one invented leader can open.

## 3. Label (administrator step)

The model writes a one-line description for every file and folder. Only labelled files can ever be found.
```
python -m kf.labeler --data testdata
```
About 4 minutes for the 249 test files on an RTX 2080 Ti. Try `--limit 20` first. Read `testdata/filemap.md` to check the labels. Run it again after files or permissions change; unchanged files are reused. A file that is missing from `filemap.md` was skipped (see the messages in the terminal). The labels are the same for every profile, so this step runs once.

## 4. Vectorize (administrator step)

```
python -m kf.indexer --data testdata [--profile low]
```
Takes seconds to a few minutes. Run it again after every labeler run. Indexes are kept per embedding model in `testdata/index/<model>/` (for example `snowflake-arctic-embed_33m/`), so each profile needs its own index: run this once with each `--profile` you use. If the index for the profile's model is missing, or the finder thresholds and the index belong to different models, the error message names the command to run.

## 5. Run as a user

**In the web window (recommended):**
```
python -m kf.web --data testdata
```
One shell does everything. It starts Ollama if it is not running, serves the page on this computer only, and opens a window. Pick a test user on the left, ask a question, then switch user and ask the same thing. Answers appear as they are written. The **Model** selector in the sidebar switches the chat model (and the embedding model, when more than one has an index and tuned thresholds) for your browser session. Stop with **Ctrl+C**: that also stops an Ollama it started. Options: `--port 8765`, `--no-browser` (just print the address), `--no-ollama`, `--profile low` (optional; see step 1.3).

When `kf.web` starts Ollama itself, it applies the profile's server settings (one request at a time, two models loaded, a smaller KV cache). An Ollama that was already running (for example the macOS app) keeps its own settings: `windows-mac.md` says how to set them.

**In the terminal:**
```
python -m kf.workspace users --data testdata                  # people, roles and the drives each can open
python -m kf.expert --user lukas.gallagher --data testdata [--profile low]    # an empty line ends the chat; --debug prints what the model is sent
```

The generated data has three kinds of people, each with one role:

| Kind | Role | Example | Opens |
|---|---|---|---|
| Board | `test.board` | `lukas.gallagher` | every drive |
| Leader | `test.leader` | `sofia.rossi` (Com: FLC), `luca.schmidt` (Com: AC) | `01_Leaders`, `Archive`, `Members` and own committee's drive |
| Committee member | `test.committee_member` | `aoife.wojcik` | `Members` only |

On top of that, `shares.yaml` gives some people single files and whole subfolders of other drives, so partial access can be tried: that is why a committee member's "Drives you can open" list is short while a note lists drives with shared files.

Ask each of them the same things (answers shown are from the generated data, with the `high` profile):

| Question | Board | Leader of FLC | Leader of AC | Committee member |
|---|---|---|---|---|
| Who is responsible for guest registration at Career Fair 2024? (`01_Leaders`) | answer + source | answer + source | answer + source | no answer, notice: *File(s) inside Drive 01_Leaders may match; you do not have permission. Ask: Leaders coordinator* |
| Who is responsible for first aid at Freshers Week 2026? (`Com: FLC`) | answer + source | answer + source | no answer, notice for `Com: FLC` | no answer, notice for `Com: FLC` |
| What is the deadline for the Welcome Cruise 2026 poster design? (`Board`) | answer + source | no answer, notice for `Board` | no answer, notice for `Board` | no answer, notice for `Board` |
| What is the venue booking reference for Career Fair 2025? (`Members`) | answer + source | answer + source | answer + source | answer + source |
| What is my role? / What drives do I have access to? | their own roles and drives | | | |

A notice names only the drive and whom to ask, never file names or counts. It appears for most, not all, questions the person cannot answer (the benchmark reports the rate). Follow-ups work: *"And what is the deadline for that event's sponsor report?"*

## 6. Automated checks (generated data only)

```
python evals/run_suite.py --quick      # about 5 minutes: tests, zero-leak and no-personal-data checks, accuracy; writes evals/suite_report.md
python evals/demo.py                   # about 3 minutes: the same questions as six people; writes evals/demo_transcript.md
python evals/run_suite.py --quick --profile low   # the same checks with another profile; writes evals/suite-low/ and evals/suite_report-low.md
```
These need the generated data in `testdata/` and write into `evals/`; do not run them on real files.

## If something fails

| Message or symptom | Fix |
|---|---|
| `No module named 'kf'` | The project is not installed in this environment: `pip install -e ".[dev]"` (step 1.2), with the environment active. |
| `unknown user` | The id is not in this data. List the ids: `python -m kf.workspace users --data testdata`. |
| `... is missing: run the labeler and the indexer first` | Steps 3 and 4 have not run for this `--data` folder. |
| Connection refused to localhost:11434 | Ollama is not running. `python -m kf.web` starts it; for the other commands start it yourself. |
| Model not found / "Missing models" at web start | Pull the two models of the profile in use (step 1.4): `qwen3:8b` and `nomic-embed-text` for `high`, and so on. |
| `no index for <model>` or "thresholds are tuned for ... but the index was built with ..." | Build that profile's index: `python -m kf.indexer --data testdata --profile low` (use the profile you run with). |
| Every answer is "I could not find anything" | The labeler or indexer has not run or labelled nothing: check `filemap.md` and the labeler's messages. |
| `no drive folders found` | The files must be in `<data>/drive/<Drive folder>/...`. |
| Address already in use | Another demo is running: `python -m kf.web --port 8766`. |
| Too slow | Use a lower profile, for example `--profile low` (labels are shared, so only the indexer step is needed for it). Do not use `KF_CHAT_MODEL=qwen3:4b`: in Ollama it is a thinking-only model and writes its reasoning into the answers. For a smaller instruct model set `KF_CHAT_MODEL=qwen3:4b-instruct` (Windows: `$env:KF_CHAT_MODEL="qwen3:4b-instruct"`). |
| Too slow / unsure which profile | `python -m kf.doctor` measures this machine and suggests a profile (`--profile low`, `mid` or `high`). Paste its output block when asking for help. |

Windows and macOS: not tested yet. What was fixed and what to check is in `windows-mac.md`.
