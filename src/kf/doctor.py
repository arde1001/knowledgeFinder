"""Hardware check: which profile fits this machine and how fast it really runs.

    python -m kf.doctor [--profile NAME] [--no-measure]

Prints the system, the Ollama state and (unless --no-measure) timings of the profile's chat and embedding models, then a
profile suggestion, all inside one `--- kf.doctor ---` block to paste back. No hostname, user name or path is included.
An answer turn is estimated as 750 prompt tokens + 30 output tokens, the measured averages in evals/profile_benchmark.md.
"""

import argparse
import ctypes
import os
import platform
import shutil
import subprocess
import time

import requests

from kf import llm, profiles

ORDER = ["low", "mid", "high"]
TURN_PROMPT_TOKENS, TURN_OUT_TOKENS, SLOW_TURN_S = 750, 30, 15
EVICT_LOAD_S = 0.5  # a chat call this slow to start right after the embedder ran had to reload its model
SENTENCE = "The synthetic committee reviews item {n} of the sample agenda and notes the owner and the deadline. "


class _MemStatus(ctypes.Structure):  # Windows MEMORYSTATUSEX
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in "abcdefg"]


def ram_gb():
    """Total RAM in GiB (a 16 GB Mac reports 16.0), or None."""
    try:
        if os.name == "nt":
            s = _MemStatus()
            s.length = ctypes.sizeof(s)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return round(s.a / 1024**3, 1) or None
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (OSError, ValueError, AttributeError):
        return None


def gpu():
    """{'kind': 'nvidia' | 'apple' | None, 'name', 'vram_gb'}."""
    if shutil.which("nvidia-smi"):
        try:
            q = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
            rows = [l.rsplit(",", 1) for l in subprocess.run(q, capture_output=True, text=True, timeout=15).stdout.splitlines() if "," in l]
            name, mib = max(rows, key=lambda r: float(r[1].split()[0]))
            return {"kind": "nvidia", "name": name.strip(), "vram_gb": round(float(mib.split()[0]) / 1024, 1)}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return {"kind": "apple", "name": "Apple Silicon (Metal, unified memory)", "vram_gb": None}
    return {"kind": None}


def by_hardware(g, ram):
    """The profile table: NVIDIA by VRAM, Apple Silicon by unified RAM, anything else is low."""
    if g["kind"] == "nvidia":
        return "high" if g["vram_gb"] >= 10 else "mid" if g["vram_gb"] >= 6 else "low"
    if g["kind"] == "apple" and ram:
        return "high" if ram >= 24 else "mid" if ram >= 16 else "low"
    return "low"


def turn_seconds(prefill, gen):
    return TURN_PROMPT_TOKENS / prefill + TURN_OUT_TOKENS / gen


def evicted(call):
    return call.get("load_duration", 0) / 1e9 > EVICT_LOAD_S


def spilled(ps, model):
    """Part of the loaded chat model runs on the CPU (needs a GPU to mean anything)."""
    m = next((m for m in ps.get("models", []) if m.get("name") in (model, f"{model}:latest")), None)
    return bool(m) and m["size_vram"] < m["size"]


def suggest(hw, measured=None):
    """Hardware's profile, or one step below the measured profile if its answers are slow or spill to the CPU."""
    if not measured:
        return hw
    name, slow, spill = measured
    return ORDER[max(ORDER.index(name) - int(slow or spill), 0)]


def filler(chars, start=0):
    s, n = "", start
    while len(s) < chars:
        s, n = s + SENTENCE.format(n=n), n + 1
    return s[:chars]


def rate(count, ns):
    return count / (ns / 1e9) if count and ns else 0.0


def api(method, path, **kw):
    """JSON of an Ollama call, or None when Ollama does not answer."""
    try:
        r = getattr(requests, method)(f"{llm.URL}{path}", **kw)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def chat_call(model, prompt, num_ctx, n_predict):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": n_predict}}
    return api("post", "/api/chat", json=body, timeout=900)


def measure(p, g):
    """Run the timings for profile p. Returns (lines, (slow, spill) or None)."""
    out = []
    prompt = f"Run {time.time_ns()}. " + filler(5500) + "\nCount from one to fifty in words."  # nonce defeats Ollama's prompt cache
    first = chat_call(p.chat_model, prompt, p.num_ctx, 64)
    if not first:
        return ["measurement: the chat call failed"], None
    prefill, gen = rate(first.get("prompt_eval_count"), first.get("prompt_eval_duration")), rate(first.get("eval_count"), first.get("eval_duration"))
    out += [f"chat prompt tokens: {first.get('prompt_eval_count')}", f"chat prefill tok/s: {prefill:.0f}", f"chat generation tok/s: {gen:.1f}",
            f"chat load s: {first.get('load_duration', 0) / 1e9:.1f}"]
    chunks = [filler(900, i * 10) for i in range(32)]
    t0 = time.perf_counter()
    emb = api("post", "/api/embed", json={"model": p.embed_model, "input": chunks}, timeout=900)
    secs = time.perf_counter() - t0 - (emb or {}).get("load_duration", 0) / 1e9
    out.append(f"embed chunks/s: {32 / secs:.1f}" if emb and secs > 0 else "embed chunks/s: failed")
    second = chat_call(p.chat_model, "Say OK.", p.num_ctx, 2) or {}
    ev = evicted(second)
    out.append(f"chat reload after embed s: {second.get('load_duration', 0) / 1e9:.1f}")
    if ev:
        out.append("warning: the chat model was unloaded to load the embedder. Set OLLAMA_MAX_LOADED_MODELS=2 for Ollama and restart it "
                   "(Ollama macOS app: `launchctl setenv OLLAMA_MAX_LOADED_MODELS 2`, then quit and reopen the app).")
    spill = bool(g["kind"]) and spilled(api("get", "/api/ps", timeout=10) or {}, p.chat_model)
    if spill:
        out.append("warning: part of the chat model runs on the CPU (it does not fit in GPU memory).")
    if not (prefill and gen):
        return out + ["measurement: no usable timings"], None
    turn = turn_seconds(prefill, gen)
    out.append(f"estimated answer turn s: {turn:.1f}")
    return out, (turn > SLOW_TURN_S, spill)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kf.doctor", description="Check this machine and suggest a hardware profile.")
    profiles.add_argument(ap)
    ap.add_argument("--no-measure", action="store_true", help="skip the timings (system, Ollama state and a hardware-based suggestion only)")
    args = ap.parse_args(argv)
    g, ram = gpu(), ram_gb()
    hw = by_hardware(g, ram)
    os_name = f"{platform.system()} {platform.mac_ver()[0] or platform.release()}"
    out = ["--- kf.doctor ---", f"os: {os_name}", f"cpu: {platform.machine()}, {os.cpu_count()} logical",
           f"ram GB: {ram if ram else 'unknown'}", f"gpu: {g['name'] + (f', {g['vram_gb']} GB VRAM' if g['vram_gb'] else '') if g['kind'] else 'none (CPU only)'}"]
    try:
        p = profiles.activate(args.profile or hw)
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))
    version = api("get", "/api/version", timeout=5)
    code = 0
    if not version:
        out += ["ollama: not answering. Start it with `ollama serve` (or open the Ollama app) and run this again.", f"suggested profile (from hardware): {hw}"]
        code = 1
    else:
        have = {m["name"] for m in (api("get", "/api/tags", timeout=10) or {}).get("models", [])}
        missing = [m for m in (p.chat_model, p.embed_model) if m not in have and f"{m}:latest" not in have]
        out += [f"ollama: {version.get('version')}", f"profile measured: {p.name} ({p.chat_model} + {p.embed_model}, num_ctx {p.num_ctx})"]
        measured = None
        if missing:
            out += [f"missing models: run `ollama pull {m}`" for m in missing]
        elif not args.no_measure:
            print("Measuring (the first call loads the models; a slow machine can take a few minutes)...", flush=True)
            lines, flags = measure(p, g)
            out += lines
            measured = (p.name, *flags) if flags else None
        best = suggest(hw, measured)
        why = "from hardware" if not measured else f"measured {p.name}: " + ("slow answers" if measured[1] else "spills to CPU" if measured[2] else "fast enough")
        out.append(f"suggested profile: {best} ({why}); use `--profile {best}` or KF_PROFILE={best}")
    print("\n".join(out + ["--- kf.doctor ---"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
