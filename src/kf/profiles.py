"""Hardware profiles: which models and how much work per step (profiles.yaml, docs/system-requirements.md).

Precedence: KF_CHAT_MODEL / KF_EMBED_MODEL > the chosen profile (--profile or KF_PROFILE) > `high`, which is the
setting the project was built and tuned with. Every component reads `current()`, so one choice applies everywhere.
"""

import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import yaml

PATH = Path("profiles.yaml")


@dataclass(frozen=True)
class Profile:
    name: str = "high"
    chat_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"
    finder: str = "finder.yaml"  # finder thresholds tuned for embed_model
    num_ctx: int = 8192  # model context in tokens; the KV cache for it is held in (V)RAM
    workers: int = 4  # parallel model calls in the labeler and the corpus generator
    label_chars: int = 3000  # characters of a file shown to the labeler
    excerpt_chars: int = 6000  # characters of excerpts in an answer prompt
    answer_tokens: int = 400  # longest answer
    history_turns: int = 4  # question/answer pairs kept for follow-ups
    ollama_env: dict = field(default_factory=dict)  # server settings when kf.web starts Ollama itself


_active = None


def load(name="high", path=PATH):
    path = Path(path)
    if not path.exists():
        if name == "high":
            return Profile()
        raise FileNotFoundError(f"{path} not found: run from the repository root or pass the profile file")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if name not in data:
        raise ValueError(f"unknown profile {name!r}; choose one of {sorted(data)}")
    values = data[name] or {}
    unknown = set(values) - {f.name for f in fields(Profile)}
    if unknown:
        raise ValueError(f"unknown settings in profile {name!r}: {sorted(unknown)}")
    return Profile(name=name, **values)


def activate(name=None, path=PATH, **overrides):
    """Choose the profile for this process. Environment model overrides win over the file; keyword overrides win over both."""
    global _active
    p = load(name or os.environ.get("KF_PROFILE") or "high", path)
    env = {"chat_model": os.environ.get("KF_CHAT_MODEL"), "embed_model": os.environ.get("KF_EMBED_MODEL")}
    _active = replace(p, **{k: v for k, v in env.items() if v}, **overrides)
    return _active


def current():
    return _active or activate()


def add_argument(ap):
    ap.add_argument("--profile", help="hardware profile from profiles.yaml: low, mid or high (default: KF_PROFILE or high)")


def slug(model):
    """File-name form of a model name: `nomic-embed-text:latest` -> `nomic-embed-text`, `a/b:c` -> `a_b_c`."""
    return model.removesuffix(":latest").replace("/", "_").replace(":", "_")
