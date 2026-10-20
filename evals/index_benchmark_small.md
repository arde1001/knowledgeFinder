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
