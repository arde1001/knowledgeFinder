"""Run every automated check of the project and write one pass/fail report.

    PYTHONPATH=src:evals .venv/bin/python evals/run_suite.py [--quick] [--profile low]

Runs the unit tests and the four benchmarks that carry hard assertions (zero leaks, zero PII, notice format). A benchmark
exits non-zero when an assertion fails. Each writes its report under evals/suite/ (the committed benchmark files in
evals/ are the tuned runs and are not overwritten). `--quick` shrinks the expert benchmark to 10 questions per persona.
`--profile` runs every check with that hardware profile's models (reports in evals/suite-<profile>/ and suite_report-<profile>.md).
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent


def checks(out):
    return [
        ("unit tests", [sys.executable, "-m", "pytest", "-q"], None),
        ("leak and PII test, every user x every question (no LLM)", [sys.executable, str(HERE / "bench_leaks.py"), "--out", str(out / "leaks.md")], "leaks.md"),
        ("finder: leaks, denial format, retrieval accuracy", [sys.executable, str(HERE / "bench_finder.py"), "--out", str(out / "finder.md")], "finder.md"),
        ("retriever: PII-free context, answer in context", [sys.executable, str(HERE / "bench_retriever.py"), "--out", str(out / "retriever.md")], "retriever.md"),
        ("expert: real prompts scanned for leaks and PII, answer quality", [sys.executable, str(HERE / "bench_expert.py"), "--out", str(out / "expert.md")], "expert.md"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--profile", help="hardware profile for every check (default: KF_PROFILE or high)")
    a = ap.parse_args()
    profile = a.profile or os.environ.get("KF_PROFILE") or "high"
    suffix = "" if profile == "high" else f"-{profile}"
    out = HERE / f"suite{suffix}"
    out.mkdir(exist_ok=True)
    rows = ["| check | result | seconds | report |", "|---|---|---|---|"]
    failed = []
    for name, cmd, report in checks(out):
        if a.quick and report == "expert.md":
            cmd = cmd + ["--per-persona", "10", "--pairs", "8"]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, cwd=HERE.parent, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONPATH": os.pathsep.join(["src", "evals"]), "PYTHONUTF8": "1", "KF_PROFILE": profile})
        secs = time.perf_counter() - t0
        ok = r.returncode == 0
        if not ok:
            failed.append((name, (r.stdout + r.stderr)[-1500:]))
        rows.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {secs:.0f} | {f'suite{suffix}/' + report if report else '-'} |")
        print(rows[-1], flush=True)
    text = f"# Eval suite (profile {profile})\n\n" + ("All checks passed.\n\n" if not failed else "FAILED: " + ", ".join(n for n, _ in failed) + "\n\n") + "\n".join(rows) + "\n"
    for name, tail in failed:
        text += f"\n## {name}\n\n```\n{tail}\n```\n"
    (HERE / f"suite_report{suffix}.md").write_text(text, encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
