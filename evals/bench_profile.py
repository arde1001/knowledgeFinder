"""Step-cost benchmark: how long each pipeline step takes for a (chat model, embedding model, device) combination.

    PYTHONPATH=src:evals .venv/bin/python evals/bench_profile.py --run qwen3:8b,nomic-embed-text,gpu --run qwen3:8b,nomic-embed-text,cpu

`cpu` forces Ollama onto the processor (`num_gpu: 0`) with `--threads` threads (default 4), a stand-in for a 4-core
laptop or an Intel Mac. Per run: cold model loads, a full index build, labelling a sample of files, and expert turns
(first questions plus follow-ups, which add the rewrite call). Timings come from Ollama's own response fields.
Writes evals/profile_benchmark.md. Quality is not measured here: see bench_finder / bench_expert.
"""

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

import requests

import bench_finder as bf
from kf import filemap, labeler, llm, profiles
from kf.expert import Expert
from kf.extract import extract_text
from kf.finder import Finder
from kf.indexer import Index, build_index
from kf.perms import Policy

DATA = bf.DATA
FOLLOW_UP = "And who should I contact about that event?"


class Recorder:
    """Stands in for `requests` inside kf.llm: adds device options to every call and keeps Ollama's timing fields."""

    def __init__(self, options):
        self.options, self.calls = options, []

    def post(self, url, json=None, **kw):
        json = {**json, "options": {**json.get("options", {}), **self.options}}
        t0 = time.perf_counter()
        r = requests.post(url, json=json, **kw)
        if r.ok:
            self.calls.append({"url": url, "wall": time.perf_counter() - t0, **{k: v for k, v in r.json().items() if k.endswith(("_count", "_duration"))}})
        return r


def unload(*models):
    for m in models:
        requests.post(f"{llm.URL}/api/generate", json={"model": m, "keep_alive": 0}, timeout=60)


def resident(model):
    ps = requests.get(f"{llm.URL}/api/ps", timeout=10).json().get("models", [])
    m = next((m for m in ps if m["name"] in (model, f"{model}:latest")), None)
    return (m["size"] / 1e9, m["size_vram"] / 1e9) if m else (0.0, 0.0)


def rates(calls):
    """Mean prompt tokens, prefill tok/s, generation tok/s over chat calls."""
    calls = [c for c in calls if c.get("eval_count")]
    pre = [c["prompt_eval_count"] / (c["prompt_eval_duration"] / 1e9) for c in calls if c.get("prompt_eval_duration")]
    gen = [c["eval_count"] / (c["eval_duration"] / 1e9) for c in calls if c.get("eval_duration")]
    mean = lambda xs: statistics.mean(xs) if xs else 0.0
    return mean([c.get("prompt_eval_count", 0) for c in calls]), mean(pre), mean(gen)


def run(chat, embed, device, threads, n_questions, n_followups, n_label, config):
    rec = Recorder({"num_gpu": 0, "num_thread": threads} if device == "cpu" else {})
    llm.requests = rec
    profiles.activate(chat_model=chat, embed_model=embed)  # the rest (num_ctx, prompt sizes) from KF_PROFILE
    unload(chat, embed)
    row = {"chat": chat, "embed": embed, "device": device}

    # cold loads (the files are in the page cache after the first run, as on any second start)
    llm.chat([{"role": "user", "content": "Say OK."}], max_tokens=2)
    row["load_chat_s"] = rec.calls[-1]["load_duration"] / 1e9
    llm.embed(["warm up"], embed)
    row["load_embed_s"] = rec.calls[-1]["load_duration"] / 1e9

    # index build
    fm, policy = filemap.load(DATA / "filemap.json"), Policy.load(DATA)
    out = Path(tempfile.mkdtemp()) / "index"
    t0 = time.perf_counter()
    build_index(DATA / "drive", fm, policy, out, lambda t: llm.embed_documents(t, embed), embed, True)
    row["index_s"] = time.perf_counter() - t0
    index_chunks = len(json.loads((out / "chunks.json").read_text(encoding="utf-8"))["chunks"])
    row["chunks_per_s"] = index_chunks / row["index_s"]

    # labelling a sample (the labeler's own prompt and limits)
    sample = sorted(fm["files"])[:: max(1, len(fm["files"]) // n_label)][:n_label]
    rec.calls.clear()
    t0 = time.perf_counter()
    for rel in sample:
        labeler.llm_describe(rel, extract_text(DATA / "drive" / rel)[: profiles.current().label_chars])
    row["label_s_per_file"] = (time.perf_counter() - t0) / len(sample)
    row["label_prompt_tok"], row["label_prefill_tps"], row["label_gen_tps"] = rates(rec.calls)

    # expert turns as the superuser, with this run's index
    everyone_policy, _, personas, _, _ = bf.load(config)
    finder = Finder(everyone_policy, fm, Index.load(out), DATA / "drive", config)
    qa = bf.read_jsonl("qa.jsonl")
    qa = qa[:: max(1, len(qa) // n_questions)][:n_questions]
    turns, answer_calls, rewrite_s = [], [], []
    for i, item in enumerate(qa):
        expert = Expert(finder)
        questions = [item["question"]] + ([FOLLOW_UP] if i < n_followups else [])
        for q in questions:
            rec.calls.clear()
            t0 = time.perf_counter()
            expert.ask(personas["superuser"], q)
            turns.append(time.perf_counter() - t0)
            chats = [c for c in rec.calls if c["url"].endswith("/api/chat")]
            answer_calls.append(chats[-1])
            if len(chats) == 2:
                rewrite_s.append(chats[0]["wall"])
    row["turn_s_mean"] = statistics.mean(turns)
    row["turn_s_max"] = max(turns)
    row["answer_prompt_tok"], row["answer_prefill_tps"], row["answer_gen_tps"] = rates(answer_calls)
    row["answer_out_tok"] = statistics.mean(c.get("eval_count", 0) for c in answer_calls)
    row["first_token_s"] = statistics.mean(c.get("prompt_eval_duration", 0) / 1e9 for c in answer_calls)
    row["rewrite_s"] = statistics.mean(rewrite_s) if rewrite_s else 0.0
    row["chat_gb"], row["chat_vram_gb"] = resident(chat)
    row["embed_gb"], _ = resident(embed)
    return row


COLUMNS = [
    ("chat", "chat model", "{}"), ("embed", "embedder", "{}"), ("device", "device", "{}"),
    ("load_chat_s", "chat load s", "{:.1f}"), ("load_embed_s", "embed load s", "{:.1f}"),
    ("index_s", "index s", "{:.1f}"), ("chunks_per_s", "chunks/s", "{:.0f}"),
    ("label_s_per_file", "label s/file", "{:.1f}"), ("label_prefill_tps", "label prefill tok/s", "{:.0f}"),
    ("turn_s_mean", "turn s (mean)", "{:.1f}"), ("turn_s_max", "turn s (max)", "{:.1f}"),
    ("first_token_s", "answer prefill s", "{:.1f}"), ("answer_prompt_tok", "answer prompt tok", "{:.0f}"),
    ("answer_out_tok", "answer out tok", "{:.0f}"), ("answer_prefill_tps", "answer prefill tok/s", "{:.0f}"),
    ("answer_gen_tps", "gen tok/s", "{:.1f}"), ("rewrite_s", "rewrite s", "{:.1f}"),
    ("chat_gb", "chat RAM GB", "{:.1f}"), ("chat_vram_gb", "chat VRAM GB", "{:.1f}"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True, help="CHAT,EMBED,DEVICE (device: gpu or cpu); repeatable")
    ap.add_argument("--threads", type=int, default=4, help="CPU threads for cpu runs")
    ap.add_argument("--questions", type=int, default=8)
    ap.add_argument("--followups", type=int, default=2)
    ap.add_argument("--label-files", type=int, default=8)
    ap.add_argument("--config", help="finder thresholds for the runs' embedder (default: the profile's)")
    ap.add_argument("--out", default=str(Path(__file__).parent / "profile_benchmark.md"))
    a = ap.parse_args()
    rows = []
    for spec in a.run:
        chat, embed, device = spec.split(",")
        rows.append(run(chat, embed, device, a.threads, a.questions, a.followups, a.label_files, bf.config(a.config)))
        print(json.dumps(rows[-1]), flush=True)
    lines = ["| " + " | ".join(h for _, h, _ in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(f.format(r[k]) for k, _, f in COLUMNS) + " |" for r in rows]
    note = (f"\n{a.questions} questions + {a.followups} follow-ups as the superuser, {a.label_files} labelled files; "
            f"cpu = `num_gpu: 0, num_thread: {a.threads}` on an i7-7700K (4 cores, DDR4); gpu = RTX 2080 Ti 22 GB.\n")
    Path(a.out).write_text("\n".join(lines) + "\n" + note, encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
