# Retriever benchmark

zero planted PII strings in any context, nothing dropped (asserted).

| persona | setting | readable q | source returned | answer in context | answer in context given the source was returned | chars of context (mean / p95) | retrieval ms (mean / p95) |
|---|---|---|---|---|---|---|---|
| superuser | best, 2 per source | 87 | 0.989 | 0.989 | 1.000 | 887 / 1656 | 7.7 / 20.2 |
| superuser | best, 1 per source | 87 | 0.989 | 0.989 | 1.000 | 828 / 1580 | 0.4 / 0.7 |
| superuser | head (first chunks), 2 per source | 87 | 0.989 | 0.989 | 1.000 | 886 / 1656 | 0.4 / 1.0 |
| member | best, 2 per source | 26 | 1.000 | 1.000 | 1.000 | 914 / 1656 | 0.5 / 0.9 |
| member | best, 1 per source | 26 | 1.000 | 1.000 | 1.000 | 908 / 1579 | 0.5 / 0.9 |
| member | head (first chunks), 2 per source | 26 | 1.000 | 1.000 | 1.000 | 914 / 1656 | 0.5 / 1.2 |
| leader | best, 2 per source | 60 | 0.983 | 0.983 | 1.000 | 894 / 1656 | 0.4 / 0.8 |
| leader | best, 1 per source | 60 | 0.983 | 0.983 | 1.000 | 855 / 1580 | 0.5 / 1.2 |
| leader | head (first chunks), 2 per source | 60 | 0.983 | 0.983 | 1.000 | 893 / 1656 | 0.5 / 1.3 |
| other_leader | best, 2 per source | 61 | 0.984 | 0.984 | 1.000 | 838 / 1394 | 0.4 / 0.9 |
| other_leader | best, 1 per source | 61 | 0.984 | 0.984 | 1.000 | 787 / 1337 | 0.4 / 0.9 |
| other_leader | head (first chunks), 2 per source | 61 | 0.984 | 0.984 | 1.000 | 837 / 1394 | 0.4 / 0.8 |
| sharee | best, 2 per source | 39 | 1.000 | 1.000 | 1.000 | 885 / 1763 | 0.4 / 0.9 |
| sharee | best, 1 per source | 39 | 1.000 | 1.000 | 1.000 | 854 / 1763 | 0.4 / 0.9 |
| sharee | head (first chunks), 2 per source | 39 | 1.000 | 1.000 | 1.000 | 884 / 1763 | 0.5 / 1.1 |
| guest | best, 2 per source | 21 | 1.000 | 1.000 | 1.000 | 930 / 1656 | 0.4 / 0.9 |
| guest | best, 1 per source | 21 | 1.000 | 1.000 | 1.000 | 922 / 1579 | 0.4 / 0.6 |
| guest | head (first chunks), 2 per source | 21 | 1.000 | 1.000 | 1.000 | 930 / 1656 | 0.4 / 1.0 |
