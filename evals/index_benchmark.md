> Not re-run: measured on the earlier 530-file test association (ten team drives); the choice of embedding model and label context was made on it. `python evals/bench_index.py` refreshes it (needs the other embedding models pulled).

| model | label context | chunks | build s | query ms | hit@1 | hit@3 | hit@5 | MRR@10 | hit@5 aligned | hit@5 cross-topic |
|---|---|---|---|---|---|---|---|---|---|---|
| nomic-embed-text | yes | 715 | 6.8 | 11 | 0.85 | 0.93 | 0.95 | 0.895 | 0.98 | 0.85 |
| nomic-embed-text | no | 715 | 5.8 | 11 | 0.80 | 0.96 | 0.96 | 0.878 | 0.98 | 0.91 |
| bge-m3 | yes | 715 | 13.3 | 45 | 0.78 | 0.93 | 0.97 | 0.860 | 0.99 | 0.88 |
| bge-m3 | no | 715 | 9.5 | 47 | 0.66 | 0.91 | 0.96 | 0.796 | 0.98 | 0.88 |
| qwen3-embedding:0.6b | yes | 715 | 27.3 | 28 | 0.62 | 0.85 | 0.92 | 0.742 | 0.97 | 0.74 |
| qwen3-embedding:0.6b | no | 715 | 17.3 | 28 | 0.48 | 0.77 | 0.84 | 0.624 | 0.92 | 0.50 |
