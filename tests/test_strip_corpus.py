import json
import re
from pathlib import Path

import pytest

from kf.extract import extract_text
from kf.pii import strip

DATA = Path("testdata")
pytestmark = pytest.mark.skipif(not (DATA / "pii.json").exists(), reason="corpus not generated")


def test_no_planted_pii_survives_stripping():
    """Every fake PII string planted in the corpus is gone after strip(), in every file format."""
    squash = lambda s: re.sub(r"\s+", " ", s)
    by_path = {}
    for x in json.loads((DATA / "pii.json").read_text(encoding="utf-8")):
        by_path.setdefault(x["path"], []).append(x["value"])
    leaks = []
    for path, values in by_path.items():
        text = squash(strip(squash(extract_text(DATA / "drive" / path))))
        leaks += [(path, v) for v in values if squash(v) in text]
    assert leaks == [], leaks[:5]


def test_stripping_keeps_the_planted_facts():
    """Answers to the Q&A set are not damaged by PII stripping."""
    squash = lambda s: re.sub(r"\s+", " ", s)
    lost = []
    for line in (DATA / "qa.jsonl").read_text(encoding="utf-8").splitlines():
        q = json.loads(line)
        text = squash(strip(squash(extract_text(DATA / "drive" / q["path"]))))
        if squash(q["answer"]) not in text:
            lost.append(q["answer"])
    assert lost == [], lost[:5]
