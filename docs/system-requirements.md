# System requirements and expected speed

Three hardware profiles are defined in `profiles.yaml`. Pick one with `--profile low|mid|high` on any command (or set
`KF_PROFILE`). `python -m kf.doctor` measures this machine and suggests one. `KF_CHAT_MODEL` and `KF_EMBED_MODEL` still
override the models of the profile.

## Profiles

| Profile | Chat model | Embedding model | Chat model memory (GB, measured) | Context used | Disk (about) |
|---|---|---|---|---|---|
| `high` | `qwen3:8b` | `nomic-embed-text` | 6.3 | 8192 | 10 GB |
| `mid` | `qwen3:4b-instruct` | `nomic-embed-text` | 3.6 | 6144 | 6 GB |
| `low` | `qwen3:1.7b` | `snowflake-arctic-embed:33m` | 1.9 | 4096 | 4 GB |

The memory column is what Ollama reports for the chat model with the profile's context (the context's cache is part
of it). The embedding model adds 0.3 GB (`nomic-embed-text`) or about 0.1 GB (`snowflake-arctic-embed:33m`).

`high` is the setting the project was built and tuned with. `low` also uses shorter label input and excerpts, two history
turns, and labels one file at a time. Each profile needs its own index (`python -m kf.indexer --data testdata --profile NAME`).
The labels are the same for all profiles.

Pull the two models of the profile before you use it:

```bash
# high
ollama pull qwen3:8b
ollama pull nomic-embed-text

# mid
ollama pull qwen3:4b-instruct
ollama pull nomic-embed-text

# low
ollama pull qwen3:1.7b
ollama pull snowflake-arctic-embed:33m
```

Do not use `qwen3:4b` (without `-instruct`) for these profiles. In Ollama it is a thinking-only model: it ignores
`think: false` and writes its reasoning into the answers.

## Minimum hardware

All profiles need Python 3.11 or newer and Ollama.

- **`low`:** 8 GB RAM. A 4-core x86-64 CPU with AVX2 (Intel from Haswell in 2013 on, AMD from 2015 on), or any Apple
  Silicon Mac with 8 GB. Intel Macs have no usable GPU for Ollama, so they run this profile on the CPU.
- **`mid`:** 16 GB Apple Silicon Mac, or an NVIDIA GPU with 6 to 8 GB VRAM.
- **`high`:** an NVIDIA GPU with 10 GB VRAM or more (the project was tuned on an RTX 2080 Ti with 22 GB), or Apple Silicon
  with 24 GB or more.

Windows or Linux with an NVIDIA GPU under 6 GB, or without an NVIDIA GPU, also use `low`.

## Measured speed

Measured on the development PC (`evals/profile_benchmark*.md`, `evals/bench_profile.py`). **CPU** = Ollama forced onto
4 threads of an i7-7700K (4 cores, DDR4, 2017), a stand-in for a 4-core laptop or an Intel Mac. **GPU** = RTX 2080 Ti
22 GB. An answer turn is a question to the expert: about 700 prompt tokens and a short answer. Labelling 249 files is
seconds per file times 249, one file at a time, plus about 15 % for the folders.

| Profile | Device | Answer turn, mean / slowest | Wait before the first word | Follow-up rewrite | Label one file | Label 249 files | Index 317 chunks | Chat model memory |
|---|---|---|---|---|---|---|---|---|
| `high` | GPU | 0.5 / 1.0 s | 0.2 s | 0.3 s | 0.6 s | about 3 min | 3 s | 6.3 GB |
| `high` | CPU | 32 / 76 s | 25 s | 9 s | 24 s | about 1 h 50 min | 62 s | 6.7 GB |
| `mid` | GPU | 0.4 / 0.7 s | 0.1 s | 0.2 s | 0.3 s | about 1.5 min | 3 s | 3.6 GB |
| `mid` | CPU | 17 / 41 s | 13 s | 4 s | 11 s | about 55 min | 69 s | 3.6 GB |
| `low` | GPU | 0.4 / 1.3 s | < 0.1 s | 0.1 s | 0.2 s | about 1 min | 3 s | 1.7 GB |
| `low` | CPU | 6 / 11 s | 4 s | 1.7 s | 5 s | about 25 min | 18 s | 1.9 GB |

Plus a few seconds to load the models once (the web demo does it at start). The web demo streams the answer, so the
words start to appear after the "wait before the first word" column.

## Estimated speed on other machines

Not measured: these are estimates from memory bandwidth and published llama.cpp speeds, for the profile we would
choose on each machine. Run `python -m kf.doctor` there and replace them with real numbers.

| Machine | Profile | Answer turn | Label 249 files |
|---|---|---|---|
| 4-core laptop without NVIDIA (Windows/Linux), on mains power | `low` | 6–12 s | 25–45 min |
| Intel Mac (quad-core, 2017–2020) | `low` | 7–15 s | 30–60 min |
| Apple M1/M2/M3, 8 GB | `low` | 1–3 s | 5–10 min |
| Apple M1/M2/M3, 16 GB | `mid` | 2–4 s | 8–15 min |
| Apple M-Pro/Max, 32 GB+ | `high` | 1–3 s | 5–10 min |
| Laptop with NVIDIA 6–8 GB (RTX 3060/4060) | `mid` (`high` fits in 8 GB) | about 0.5 s (`high` about 1 s) | 2–5 min |

On battery, laptops often run at half speed or less. An 8 GB machine also needs room for the browser and the
operating system, which is why `low` is the choice there even on Apple Silicon.

## What makes it slow

- **Reading the prompt.** On a CPU most of an answer's time is the prompt (prefill), not the words. With `qwen3:8b` on a
  4-core i7-7700K, about 750 prompt tokens take about 25 s before the first word (`evals/profile_benchmark.md`).
- **Embedding on a CPU.** It is about 20 times slower than on a GPU (5 against 97 chunks per second with
  `nomic-embed-text`). That is why `low` uses the 33-million-parameter `snowflake-arctic-embed:33m`, which is faster on a
  CPU with nearly the same search quality (`evals/index_benchmark_small.md`).
- **A model that does not fit in GPU memory.** Part of it then runs on the CPU, which is much slower. `kf.doctor` reports
  this. A smaller profile, or a smaller context, fixes it.
- **Two models that do not fit in RAM together.** Ollama unloads one to load the other, so every question waits for a
  reload (tens of seconds). `kf.doctor` detects this from the load times. The web demo keeps both models loaded when the
  profile's Ollama settings apply (see `docs/windows-mac.md` for macOS and Windows).

## Quality per profile

All three profiles pass every hard check: zero leaks over every user and question, no planted PII in any prompt,
the denial notice never in a prompt, and no answer to any unanswerable question (`evals/suite_report*.md`,
`evals/cutoff_benchmark*.md`). They differ in answer quality:

| | `high` (qwen3:8b + nomic) | `mid` (qwen3:4b-instruct + nomic) | `low` (qwen3:1.7b + snowflake) |
|---|---|---|---|
| Answer correct, questions the person can read | 0.96–1.00 | 0.96–1.00 | 0.93–1.00 |
| Unanswerable questions refused | 1.00 | 1.00 | 1.00 |
| Notice names the drive of the answer (restricted questions) | 0.75–0.92 | 0.75–0.92 | 0.75–0.92 |
| Casual paraphrases answered (superuser / member) | 0.98 / 0.94 | 0.98 / 0.94 | 0.96 / 0.94 |
| Questions about the own account answered (of 8) | 8 | 7 | 6 |
| Follow-up keeps the event name / answered correctly | 1.00 / 1.00 | 1.00 / 0.95 | 0.52 / 0.62 |
| Search hit@1 (file ranked first) | 0.89 | 0.89 | 0.87 |

The weak spot of `low` is follow-up questions ("and who booked it?"): the 1.7B model often fails to write the event
name into the rewritten question, so the search looks for the wrong thing. Ask follow-ups as full questions on `low`.
