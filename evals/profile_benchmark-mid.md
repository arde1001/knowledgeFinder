| chat model | embedder | device | chat load s | embed load s | index s | chunks/s | label s/file | label prefill tok/s | turn s (mean) | turn s (max) | answer prefill s | answer prompt tok | answer out tok | answer prefill tok/s | gen tok/s | rewrite s | chat RAM GB | chat VRAM GB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:4b-instruct | nomic-embed-text | cpu | 2.1 | 2.8 | 68.7 | 5 | 11.2 | 36 | 17.2 | 41.0 | 12.9 | 747 | 24 | 75 | 7.3 | 4.4 | 3.6 | 0.0 |
| qwen3:4b-instruct | nomic-embed-text | gpu | 2.9 | 0.5 | 3.0 | 105 | 0.3 | 3611 | 0.4 | 0.7 | 0.1 | 747 | 23 | 7673 | 124.6 | 0.2 | 3.6 | 3.6 |

8 questions + 2 follow-ups as the superuser, 8 labelled files; cpu = `num_gpu: 0, num_thread: 4` on an i7-7700K (4 cores, DDR4); gpu = RTX 2080 Ti 22 GB.
