# Retriever benchmark

zero planted PII strings in any context, nothing dropped (asserted).

| persona | setting | readable q | source returned | answer in context | answer in context given the source was returned | chars of context (mean / p95) | retrieval ms (mean / p95) |
|---|---|---|---|---|---|---|---|
| superuser | best, 2 per source | 87 | 0.989 | 0.989 | 1.000 | 887 / 1656 | 11.5 / 30.4 |
| superuser | best, 1 per source | 87 | 0.989 | 0.989 | 1.000 | 828 / 1580 | 6.6 / 15.3 |
| superuser | head (first chunks), 2 per source | 87 | 0.989 | 0.989 | 1.000 | 886 / 1656 | 5.0 / 10.2 |
| member | best, 2 per source | 26 | 1.000 | 1.000 | 1.000 | 914 / 1656 | 4.5 / 9.9 |
| member | best, 1 per source | 26 | 1.000 | 1.000 | 1.000 | 908 / 1579 | 3.9 / 8.8 |
| member | head (first chunks), 2 per source | 26 | 1.000 | 1.000 | 1.000 | 914 / 1656 | 4.0 / 7.8 |
| leader | best, 2 per source | 60 | 0.983 | 0.983 | 1.000 | 894 / 1656 | 4.8 / 12.4 |
| leader | best, 1 per source | 60 | 0.983 | 0.983 | 1.000 | 855 / 1580 | 4.6 / 11.8 |
| leader | head (first chunks), 2 per source | 60 | 0.983 | 0.983 | 1.000 | 893 / 1656 | 5.3 / 13.5 |
| other_leader | best, 2 per source | 61 | 0.984 | 0.984 | 1.000 | 838 / 1394 | 4.9 / 10.8 |
| other_leader | best, 1 per source | 61 | 0.984 | 0.984 | 1.000 | 787 / 1337 | 5.3 / 11.7 |
| other_leader | head (first chunks), 2 per source | 61 | 0.984 | 0.984 | 1.000 | 837 / 1394 | 4.8 / 11.3 |
| sharee | best, 2 per source | 39 | 1.000 | 1.000 | 1.000 | 885 / 1763 | 4.6 / 12.1 |
| sharee | best, 1 per source | 39 | 1.000 | 1.000 | 1.000 | 854 / 1763 | 4.4 / 9.6 |
| sharee | head (first chunks), 2 per source | 39 | 1.000 | 1.000 | 1.000 | 884 / 1763 | 4.9 / 16.8 |
| guest | best, 2 per source | 21 | 1.000 | 1.000 | 1.000 | 930 / 1656 | 4.0 / 8.4 |
| guest | best, 1 per source | 21 | 1.000 | 1.000 | 1.000 | 922 / 1579 | 4.3 / 10.4 |
| guest | head (first chunks), 2 per source | 21 | 1.000 | 1.000 | 1.000 | 930 / 1656 | 3.6 / 7.7 |
