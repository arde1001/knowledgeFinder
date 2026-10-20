# Retriever benchmark

zero planted PII strings in any context, nothing dropped (asserted).

| persona | setting | readable q | source returned | answer in context | answer in context given the source was returned | chars of context (mean / p95) | retrieval ms (mean / p95) |
|---|---|---|---|---|---|---|---|
| superuser | best, 2 per source | 87 | 0.977 | 0.977 | 1.000 | 974 / 2054 | 7.9 / 20.4 |
| superuser | best, 1 per source | 87 | 0.977 | 0.977 | 1.000 | 876 / 2054 | 0.4 / 1.0 |
| superuser | head (first chunks), 2 per source | 87 | 0.977 | 0.977 | 1.000 | 973 / 2054 | 0.5 / 1.1 |
| member | best, 2 per source | 26 | 0.962 | 0.962 | 1.000 | 913 / 1656 | 0.5 / 0.9 |
| member | best, 1 per source | 26 | 0.962 | 0.962 | 1.000 | 908 / 1579 | 0.6 / 1.4 |
| member | head (first chunks), 2 per source | 26 | 0.962 | 0.962 | 1.000 | 913 / 1656 | 0.5 / 1.0 |
| leader | best, 2 per source | 60 | 0.967 | 0.967 | 1.000 | 991 / 2337 | 0.6 / 1.5 |
| leader | best, 1 per source | 60 | 0.967 | 0.967 | 1.000 | 923 / 2337 | 0.5 / 1.3 |
| leader | head (first chunks), 2 per source | 60 | 0.967 | 0.967 | 1.000 | 990 / 2337 | 0.7 / 1.9 |
| other_leader | best, 2 per source | 61 | 0.967 | 0.967 | 1.000 | 843 / 1573 | 0.4 / 0.9 |
| other_leader | best, 1 per source | 61 | 0.967 | 0.967 | 1.000 | 780 / 1566 | 0.4 / 0.8 |
| other_leader | head (first chunks), 2 per source | 61 | 0.967 | 0.967 | 1.000 | 842 / 1573 | 0.4 / 0.9 |
| sharee | best, 2 per source | 39 | 0.974 | 0.974 | 1.000 | 932 / 1694 | 0.5 / 1.3 |
| sharee | best, 1 per source | 39 | 0.974 | 0.974 | 1.000 | 880 / 1649 | 0.5 / 1.0 |
| sharee | head (first chunks), 2 per source | 39 | 0.974 | 0.974 | 1.000 | 931 / 1694 | 0.4 / 0.7 |
| guest | best, 2 per source | 21 | 0.952 | 0.952 | 1.000 | 878 / 1495 | 0.5 / 1.2 |
| guest | best, 1 per source | 21 | 0.952 | 0.952 | 1.000 | 872 / 1495 | 0.5 / 1.0 |
| guest | head (first chunks), 2 per source | 21 | 0.952 | 0.952 | 1.000 | 878 / 1495 | 0.4 / 0.6 |
