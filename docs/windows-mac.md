# Windows and macOS: status and what to check

Everything was built and run on Linux. **Nothing has been run on Windows or macOS yet.** The four problems that were
known from reading the code are fixed (below); the list under "To check on the first real run" is what is still unproven.

## Performance on laptops and Macs

Choose the profile by hardware (`python -m kf.doctor` times this machine and suggests one; add `--no-measure` to skip the timing):

- Intel Mac: CPU only, use `low`.
- Apple Silicon with 8 GB: `low`. With 16 GB: `mid`. With 24 GB or more: `high`.
- Windows or Linux without an NVIDIA GPU: `low`. With NVIDIA: 6 to 8 GB VRAM `mid`, 10 GB or more `high`.

Pass the profile with `--profile low` (or set `KF_PROFILE=low`) and pull that profile's two models. Numbers and requirements: [`system-requirements.md`](system-requirements.md).

The web demo sets Ollama's server options only when it starts Ollama itself: one request at a time, two models loaded, flash attention and a smaller KV cache (`OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, for `low` and `mid`). An Ollama that is already running keeps its own settings, so set them yourself and restart Ollama:

- **macOS** (Ollama app): run these in Terminal, then quit the Ollama app from the menu bar and open it again.
  ```
  launchctl setenv OLLAMA_NUM_PARALLEL 1
  launchctl setenv OLLAMA_MAX_LOADED_MODELS 2
  launchctl setenv OLLAMA_FLASH_ATTENTION 1
  launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
  ```
- **Windows**: set the same four names as user environment variables, for example in PowerShell `setx OLLAMA_NUM_PARALLEL 1` (and the other three), then quit Ollama from the system tray and start it again. New terminals see the variables; already open ones do not.

## Fixed (so the demo can run on Windows)

| Problem | Fix |
|---|---|
| `str(path.relative_to(root))` gave `events\plan.md` on Windows, which the permission code rejects, so the labeler skipped every file. | `labeler.py` uses `.as_posix()`. |
| Text files were read and written without `encoding=`, so Windows used its code page (cp1252) for non-ASCII text. | Every `read_text` / `write_text` in `src/`, `evals/` and `tests/` now says `encoding="utf-8"`. The tutorial still sets `PYTHONUTF8=1` for the console. |
| `run_suite.py` set `PYTHONPATH` to `src:evals`; Windows separates paths with `;`. | It uses `os.pathsep` and runs the checks with UTF-8. |
| The symlink test needs administrator rights or Developer Mode on Windows. | It skips itself when the symlink cannot be created. |
| The corpus used folder names with a colon (`Com: FLC`), which Windows cannot store. | The drive is shown as `Com: FLC` but its folder is `Com_FLC`. |

## To check on the first real run

Please run `pip install -e ".[dev]"`, `python -m pytest -q`, `python -m kf.doctor`, the commands of the README and the web page once on each system, and report what differs. Paste the block that `kf.doctor` prints.

- **Web demo shell:** `python -m kf.web` starts Ollama as a child if it is not running and stops it on exit. **Stop it with Ctrl+C.** On Windows, closing the console window with the X may end Python without running the cleanup and leave the Ollama it started running; stop that one from the task manager or with `Stop-Process -Name ollama`.
- **Window:** the page opens in a Chrome, Edge or Chromium window without an address bar if one is installed (`--app`), otherwise in the default browser. Use `--no-browser` and open the printed address yourself if neither works.
- **Python:** 3.11 or newer. macOS ships an older one: install from python.org or Homebrew. On Windows use `py -3`.
- **PowerShell** blocks `Activate.ps1` by default: `Set-ExecutionPolicy -Scope Process Bypass`.
- **Ollama:** installers exist for both systems. On Apple Silicon it uses the GPU (Metal); Windows with an NVIDIA GPU works. Without a GPU, use `--profile low` (see above): labelling hundreds of files with `qwen3:8b` takes hours. Do not use `KF_CHAT_MODEL=qwen3:4b`: in Ollama it is a thinking-only model and writes its reasoning into the answers; `qwen3:4b-instruct` is the instruct variant. The `low` profile's embedding model is small enough for a CPU.
- **Case-insensitive file systems** (default on both): `Events/` and `events/` are the same folder, while the permission code compares folder names exactly. Use the folder names as the export gave them and keep one spelling in `drives.yaml` and `shares.yaml`.
- **Unicode normalisation (macOS):** Finder can store accented file names in decomposed form. The labeler records the names from the disk, so they stay consistent, but a hand-written `shares.yaml` must be copied from the same listing.
- **Long paths (Windows):** exports of deep Drive trees can pass 260 characters. Enable long paths (`LongPathsEnabled`) or export to a short folder such as `C:\kf\mydata`.
- **Office lock files** (`~$plan.docx`) fail text extraction. The labeler logs them and leaves them out, which is correct.
- **Console:** use Windows Terminal. The old console cannot show every character the model writes, even with `PYTHONUTF8=1`.
- **Created dates:** `kf.workspace init` uses the file's modification time. Downloaded files usually carry the download time. Put the real dates in `drive_meta.json` if you have them.

## Not affected

PDF output uses a built-in font (no font files). The file extractors (`pypdf`, `python-docx`, `openpyxl`, `python-pptx`), `numpy`, `requests` and `pyyaml` publish wheels for Windows and macOS. The web page uses only the Python standard library plus the project's own dependencies and a bundled copy of Open Sans (SIL Open Font License, `src/kf/web/static/fonts/OFL.txt`).
