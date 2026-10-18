# Windows and macOS: status and what to check

Everything was built and run on Linux. **Nothing has been run on Windows or macOS yet.** The four problems that were
known from reading the code are fixed (below); the list under "To check on the first real run" is what is still unproven.

## Fixed (so the demo can run on Windows)

| Problem | Fix |
|---|---|
| `str(path.relative_to(root))` gave `events\plan.md` on Windows, which the permission code rejects, so the labeler skipped every file. | `labeler.py` uses `.as_posix()`. |
| Text files were read and written without `encoding=`, so Windows used its code page (cp1252) for non-ASCII text. | Every `read_text` / `write_text` in `src/`, `evals/` and `tests/` now says `encoding="utf-8"`. The tutorial still sets `PYTHONUTF8=1` for the console. |
| `run_suite.py` set `PYTHONPATH` to `src:evals`; Windows separates paths with `;`. | It uses `os.pathsep` and runs the checks with UTF-8. |
| The symlink test needs administrator rights or Developer Mode on Windows. | It skips itself when the symlink cannot be created. |
| The corpus used folder names with a colon (`Com: FLC`), which Windows cannot store. | The drive is shown as `Com: FLC` but its folder is `Com_FLC`. |

## To check on the first real run

Please run `pip install -e ".[dev]"`, `python -m pytest -q`, the four commands of the README and the web page once on each system, and report what differs.

- **Web demo shell:** `python -m kf.web` starts Ollama as a child if it is not running and stops it on exit. **Stop it with Ctrl+C.** On Windows, closing the console window with the X may end Python without running the cleanup and leave the Ollama it started running; stop that one from the task manager or with `Stop-Process -Name ollama`.
- **Window:** the page opens in a Chrome, Edge or Chromium window without an address bar if one is installed (`--app`), otherwise in the default browser. Use `--no-browser` and open the printed address yourself if neither works.
- **Python:** 3.11 or newer. macOS ships an older one: install from python.org or Homebrew. On Windows use `py -3`.
- **PowerShell** blocks `Activate.ps1` by default: `Set-ExecutionPolicy -Scope Process Bypass`.
- **Ollama:** installers exist for both systems. On Apple Silicon it uses the GPU (Metal); Windows with an NVIDIA GPU works. Without a GPU, labelling hundreds of files with `qwen3:8b` takes hours: use `KF_CHAT_MODEL=qwen3:4b` (or smaller) and a small data set. The embedding model is small enough for a CPU.
- **Case-insensitive file systems** (default on both): `Events/` and `events/` are the same folder, while the permission code compares folder names exactly. Use the folder names as the export gave them and keep one spelling in `drives.yaml` and `shares.yaml`.
- **Unicode normalisation (macOS):** Finder can store accented file names in decomposed form. The labeler records the names from the disk, so they stay consistent, but a hand-written `shares.yaml` must be copied from the same listing.
- **Long paths (Windows):** exports of deep Drive trees can pass 260 characters. Enable long paths (`LongPathsEnabled`) or export to a short folder such as `C:\kf\mydata`.
- **Office lock files** (`~$plan.docx`) fail text extraction. The labeler logs them and leaves them out, which is correct.
- **Console:** use Windows Terminal. The old console cannot show every character the model writes, even with `PYTHONUTF8=1`.
- **Created dates:** `kf.workspace init` uses the file's modification time. Downloaded files usually carry the download time. Put the real dates in `drive_meta.json` if you have them.

## Not affected

PDF output uses a built-in font (no font files). The file extractors (`pypdf`, `python-docx`, `openpyxl`, `python-pptx`), `numpy`, `requests` and `pyyaml` publish wheels for Windows and macOS. The web page uses only the Python standard library plus the project's own dependencies and a bundled copy of Open Sans (SIL Open Font License, `src/kf/web/static/fonts/OFL.txt`).
