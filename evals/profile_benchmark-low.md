| chat model | embedder | device | chat load s | embed load s | index s | chunks/s | label s/file | label prefill tok/s | turn s (mean) | turn s (max) | answer prefill s | answer prompt tok | answer out tok | answer prefill tok/s | gen tok/s | rewrite s | chat RAM GB | chat VRAM GB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:1.7b | snowflake-arctic-embed:33m | cpu | 1.9 | 3.2 | 17.5 | 18 | 5.0 | 94 | 6.1 | 11.4 | 4.1 | 686 | 23 | 196 | 15.4 | 1.7 | 1.9 | 0.0 |
| qwen3:1.7b | snowflake-arctic-embed:33m | gpu | 1.6 | 0.5 | 2.7 | 119 | 0.2 | 7689 | 0.4 | 1.3 | 0.0 | 727 | 51 | 17780 | 219.9 | 0.1 | 1.7 | 1.7 |

8 questions + 2 follow-ups as the superuser, 8 labelled files; cpu = `num_gpu: 0, num_thread: 4` on an i7-7700K (4 cores, DDR4); gpu = RTX 2080 Ti 22 GB.
