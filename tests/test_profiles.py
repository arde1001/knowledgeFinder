from dataclasses import fields
from pathlib import Path

import pytest

from kf import llm, profiles
from kf.finder import Config
from kf.profiles import Profile

ROOT = Path(__file__).parent.parent
FILE = ROOT / "profiles.yaml"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    for var in ("KF_PROFILE", "KF_CHAT_MODEL", "KF_EMBED_MODEL"):
        monkeypatch.delenv(var, raising=False)
    yield
    profiles._active = None


def test_high_profile_is_the_tuned_setup_main_runs_with():
    assert profiles.load("high", FILE) == Profile()


def test_every_profile_names_all_settings_and_thresholds_tuned_for_its_embedder():
    import yaml
    data = yaml.safe_load(FILE.read_text(encoding="utf-8"))
    assert {"low", "mid", "high"} <= set(data)
    for name in data:
        p = profiles.load(name, FILE)
        assert set(data[name]) == {f.name for f in fields(Profile)} - {"name"}, name
        assert Config.load(ROOT / p.finder).tuned_for == p.embed_model, name


def test_environment_models_override_the_profile(monkeypatch):
    monkeypatch.setenv("KF_PROFILE", "low")
    monkeypatch.setenv("KF_CHAT_MODEL", "my-model")
    p = profiles.activate(path=FILE)
    assert (p.name, p.chat_model, p.num_ctx) == ("low", "my-model", profiles.load("low", FILE).num_ctx)
    assert llm.CHAT_MODEL == "my-model" and llm.EMBED_MODEL == p.embed_model


def test_flag_wins_over_environment(monkeypatch):
    monkeypatch.setenv("KF_PROFILE", "low")
    assert profiles.activate("mid", FILE).name == "mid"


def test_unknown_profile_or_setting_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unknown profile"):
        profiles.load("huge", FILE)
    bad = tmp_path / "p.yaml"
    bad.write_text("low:\n  chat_model: x\n  turbo: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="turbo"):
        profiles.load("low", bad)


def test_without_a_profile_file_only_high_is_available(tmp_path):
    assert profiles.load("high", tmp_path / "none.yaml") == Profile()
    with pytest.raises(FileNotFoundError):
        profiles.load("low", tmp_path / "none.yaml")


def test_slug():
    assert profiles.slug("nomic-embed-text:latest") == "nomic-embed-text"
    assert profiles.slug("hf.co/a/b:Q4") == "hf.co_a_b_Q4"
