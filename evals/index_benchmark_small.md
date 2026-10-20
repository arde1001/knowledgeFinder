| model | label context | chunks | build s | query ms | hit@1 | hit@3 | hit@5 | MRR@10 | hit@5 aligned | hit@5 cross-topic |
|---|---|---|---|---|---|---|---|---|---|---|
| nomic-embed-text | yes | 317 | 3.3 | 12 | 0.89 | 0.99 | 0.99 | 0.936 | 1.00 | 0.94 |
| nomic-embed-text | no | 317 | 2.7 | 12 | 0.92 | 0.99 | 1.00 | 0.956 | 1.00 | 1.00 |
| snowflake-arctic-embed:33m | yes | 317 | 3.2 | 11 | 0.87 | 0.95 | 0.98 | 0.920 | 1.00 | 0.88 |
| snowflake-arctic-embed:33m | no | 317 | 2.5 | 11 | 0.90 | 0.99 | 1.00 | 0.939 | 1.00 | 1.00 |
| granite-embedding:30m | yes | 317 | 8.5 | 13 | 0.66 | 0.87 | 0.93 | 0.776 | 0.99 | 0.71 |
| granite-embedding:30m | no | 317 | 2.3 | 13 | 0.79 | 0.89 | 0.93 | 0.852 | 1.00 | 0.65 |
| all-minilm | yes | 317 | 8.0 | 11 | 0.74 | 0.95 | 0.98 | 0.839 | 1.00 | 0.88 |
| all-minilm | no | 317 | 2.1 | 10 | 0.76 | 0.97 | 0.99 | 0.859 | 1.00 | 0.94 |

CPU speed (Ollama `num_gpu: 0, num_thread: 4` on an i7-7700K; 317 chunks, label context on / off):

| model | chunks/s (context / no context) | index build s | query ms |
|---|---|---|---|
| nomic-embed-text | 5.1 / 6.7 | 62 / 47 | 43 |
| snowflake-arctic-embed:33m | 18.6 / 23.4 | 17 / 14 | 21 |
| granite-embedding:30m | 31.3 / 43.0 | 10 / 7 | 16 |
| all-minilm | 30.8 / 40.8 | 10 / 8 | 13 |

snowflake-arctic-embed:33m is the low profile's embedder: 3.6x faster than nomic-embed-text on a CPU with almost the
same hit rate (hit@1 0.87 vs 0.89, hit@5 0.98 vs 0.99 with label context). granite and all-minilm are faster still but
lose on cross-topic questions (hit@5 0.71 / 0.88).
