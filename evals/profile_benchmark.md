# Step cost per model and device (Phase 0 baseline)

| chat model | embedder | device | chat load s | embed load s | index s | chunks/s | label s/file | label prefill tok/s | turn s (mean) | turn s (max) | answer prefill s | answer prompt tok | answer out tok | answer prefill tok/s | gen tok/s | rewrite s | chat RAM GB | chat VRAM GB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | nomic-embed-text | gpu | 4.3 | 0.5 | 3.3 | 97 | 0.6 | 2270 | 0.5 | 1.0 | 0.2 | 739 | 15 | 4869 | 82.5 | 0.3 | 6.3 | 6.3 |
| qwen3:8b | nomic-embed-text | cpu | 3.3 | 0.5 | 61.5 | 5 | 23.6 | 18 | 31.9 | 75.8 | 24.8 | 755 | 20 | 39 | 4.2 | 9.1 | 6.7 | 0.0 |
| qwen3:4b | nomic-embed-text | cpu | 2.3 | 0.3 | 61.0 | 5 | 23.5 | 36 | 71.1 | 119.0 | 12.2 | 714 | 344 | 76 | 6.4 | 22.7 | 3.9 | 0.0 |
| qwen3:1.7b | nomic-embed-text | cpu | 1.6 | 0.3 | 62.4 | 5 | 5.2 | 91 | 6.3 | 11.8 | 4.2 | 686 | 23 | 193 | 15.7 | 1.8 | 2.4 | 0.0 |
| qwen3:4b-instruct | nomic-embed-text | cpu | 2.3 | 2.2 | 64.4 | 5 | 11.8 | 34 | 18.1 | 45.0 | 13.7 | 747 | 24 | 70 | 7.2 | 4.6 | 3.9 | 0.0 |
| qwen3:4b-instruct | nomic-embed-text | gpu | 2.7 | 0.5 | 3.2 | 101 | 0.3 | 3493 | 0.4 | 0.8 | 0.1 | 747 | 23 | 7633 | 116.7 | 0.2 | 3.9 | 3.9 |

8 questions + 2 follow-ups as the superuser, 8 labelled files; cpu = `num_gpu: 0, num_thread: 4` on an i7-7700K (4 cores, DDR4); gpu = RTX 2080 Ti 22 GB.
Findings:
- CPU answers are dominated by prompt reading (prefill): about 750 prompt tokens at 39 tok/s (qwen3:8b) is 25 s before the first word.
- Embedding on CPU is about 20x slower than on the GPU (5 vs 97 chunks/s with nomic-embed-text): 1 minute for this corpus, about an hour for 15,000 real chunks.
- `qwen3:4b` in Ollama is the thinking-only 2507 model: it ignores `think: false` and writes its reasoning into the answer (344 output tokens per answer, 71 s per CPU turn). Use `qwen3:4b-instruct`.
- gemma3:4b and llama3.2:3b accept `think: false` without error on Ollama 0.33.3.
- RAM includes the 8192-token KV cache (`num_ctx` is hard-coded in kf.llm).
