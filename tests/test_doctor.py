import pytest
import requests

from kf import doctor, profiles

NV = lambda gb: {"kind": "nvidia", "name": "GPU", "vram_gb": gb}
APPLE = {"kind": "apple", "name": "Apple", "vram_gb": None}
NONE = {"kind": None}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    for var in ("KF_PROFILE", "KF_CHAT_MODEL", "KF_EMBED_MODEL"):
        monkeypatch.delenv(var, raising=False)
    yield
    profiles._active = None


@pytest.mark.parametrize("g,ram,want", [
    (NV(22), 32, "high"), (NV(10), 16, "high"), (NV(8), 32, "mid"), (NV(6), 16, "mid"), (NV(4), 32, "low"),
    (APPLE, 32, "high"), (APPLE, 24, "high"), (APPLE, 16, "mid"), (APPLE, 8, "low"), (APPLE, None, "low"),
    (NONE, 64, "low"), (NONE, None, "low"),
])
def test_hardware_rules(g, ram, want):
    assert doctor.by_hardware(g, ram) == want


def test_suggest_steps_down_one_profile_when_slow_or_spilling_and_stops_at_low():
    assert doctor.suggest("high") == "high"
    assert doctor.suggest("high", ("high", False, False)) == "high"
    assert doctor.suggest("high", ("high", True, False)) == "mid"
    assert doctor.suggest("high", ("mid", False, True)) == "low"
    assert doctor.suggest("low", ("low", True, True)) == "low"


def test_turn_estimate_uses_the_benchmark_averages():
    assert doctor.turn_seconds(750, 30) == pytest.approx(2.0)
    assert doctor.turn_seconds(39, 4.2) > doctor.SLOW_TURN_S  # qwen3:8b on 4 CPU cores (evals/profile_benchmark.md)
    assert doctor.turn_seconds(4869, 82.5) < doctor.SLOW_TURN_S


def test_eviction_is_a_reload_over_half_a_second():
    assert doctor.evicted({"load_duration": 2_000_000_000})
    assert not doctor.evicted({"load_duration": 40_000_000})
    assert not doctor.evicted({})


def test_spill_means_less_vram_than_model_size():
    ps = lambda size, vram: {"models": [{"name": "qwen3:8b", "size": size, "size_vram": vram}]}
    assert doctor.spilled(ps(6, 4), "qwen3:8b")
    assert not doctor.spilled(ps(6, 6), "qwen3:8b")
    assert not doctor.spilled({"models": []}, "qwen3:8b")
    assert not doctor.spilled(ps(6, 0), "other")


def test_filler_is_deterministic_and_synthetic():
    assert doctor.filler(900, 3) == doctor.filler(900, 3) and len(doctor.filler(900)) == 900


class Fake:
    """Stands in for `requests` in kf.doctor: canned Ollama answers, a second chat call that reloads or not."""

    def __init__(self, load2=0, vram=6, models=("qwen3:8b", "nomic-embed-text:latest")):
        self.load2, self.vram, self.models, self.chats = load2, vram, models, 0
        self.RequestException = requests.RequestException

    def get(self, url, **kw):
        body = {"/api/version": {"version": "0.9.9"}, "/api/tags": {"models": [{"name": m} for m in self.models]},
                "/api/ps": {"models": [{"name": "qwen3:8b", "size": 6e9, "size_vram": self.vram * 1e9}]}}[url.removeprefix(doctor.llm.URL)]
        return Resp(body)

    def post(self, url, **kw):
        if url.endswith("/api/embed"):
            return Resp({"load_duration": 0})
        self.chats += 1
        if self.chats == 1:
            return Resp({"prompt_eval_count": 1500, "prompt_eval_duration": 1_000_000_000, "eval_count": 64, "eval_duration": 1_000_000_000, "load_duration": 3_000_000_000})
        return Resp({"load_duration": self.load2})


class Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def run(monkeypatch, capsys, fake, g=NV(22), argv=()):
    monkeypatch.setattr(doctor, "requests", fake)
    monkeypatch.setattr(doctor, "gpu", lambda: g)
    monkeypatch.setattr(doctor, "ram_gb", lambda: 32.0)
    code = doctor.main(list(argv))
    return code, capsys.readouterr().out


def test_healthy_run_prints_numbers_and_suggests_the_hardware_profile(monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, Fake())
    assert code == 0 and "\n--- kf.doctor ---\nos: " in out and out.rstrip().endswith("--- kf.doctor ---")
    assert "chat prefill tok/s: 1500" in out and "chat generation tok/s: 64.0" in out and "embed chunks/s" in out
    assert "warning" not in out and "suggested profile: high" in out


def test_eviction_and_spill_warn_and_step_the_suggestion_down(monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, Fake(load2=3_000_000_000, vram=4))
    assert "OLLAMA_MAX_LOADED_MODELS=2" in out and "runs on the CPU" in out and "suggested profile: mid" in out


def test_missing_models_print_pull_commands_and_skip_the_timings(monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, Fake(models=("qwen3:8b",)))
    assert "ollama pull nomic-embed-text" in out and "tok/s" not in out


def test_ollama_down_still_prints_the_system_and_exits_1(monkeypatch, capsys):
    class Down(Fake):
        def get(self, url, **kw):
            raise requests.ConnectionError("no")
    code, out = run(monkeypatch, capsys, Down(), g=NONE)
    assert code == 1 and "ollama serve" in out and "gpu: none (CPU only)" in out and "suggested profile (from hardware): low" in out
