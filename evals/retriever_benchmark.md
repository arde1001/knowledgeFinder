# Retriever benchmark

zero planted PII strings in any context, nothing dropped (asserted).

| persona | setting | readable q | source returned | answer in context | answer in context given the source was returned | chars of context (mean / p95) | retrieval ms (mean / p95) |
|---|---|---|---|---|---|---|---|
| superuser | best, 2 per source | 87 | 0.989 | 0.989 | 1.000 | 887 / 1656 | 8.4 / 22.1 |
| superuser | best, 1 per source | 87 | 0.989 | 0.989 | 1.000 | 828 / 1580 | 5.3 / 12.1 |
| superuser | head (first chunks), 2 per source | 87 | 0.989 | 0.989 | 1.000 | 886 / 1656 | 5.2 / 11.5 |
| member | best, 2 per source | 26 | 1.000 | 1.000 | 1.000 | 914 / 1656 | 4.9 / 10.2 |
| member | best, 1 per source | 26 | 1.000 | 1.000 | 1.000 | 908 / 1579 | 4.1 / 8.6 |
| member | head (first chunks), 2 per source | 26 | 1.000 | 1.000 | 1.000 | 914 / 1656 | 4.4 / 8.4 |
| leader | best, 2 per source | 60 | 0.983 | 0.983 | 1.000 | 894 / 1656 | 5.3 / 13.1 |
| leader | best, 1 per source | 60 | 0.983 | 0.983 | 1.000 | 855 / 1580 | 6.5 / 13.9 |
| leader | head (first chunks), 2 per source | 60 | 0.983 | 0.983 | 1.000 | 893 / 1656 | 6.0 / 15.8 |
| other_leader | best, 2 per source | 61 | 0.984 | 0.984 | 1.000 | 838 / 1394 | 5.2 / 12.5 |
| other_leader | best, 1 per source | 61 | 0.984 | 0.984 | 1.000 | 787 / 1337 | 5.6 / 12.1 |
| other_leader | head (first chunks), 2 per source | 61 | 0.984 | 0.984 | 1.000 | 837 / 1394 | 5.6 / 11.1 |
| sharee | best, 2 per source | 39 | 1.000 | 1.000 | 1.000 | 885 / 1763 | 5.1 / 14.8 |
| sharee | best, 1 per source | 39 | 1.000 | 1.000 | 1.000 | 854 / 1763 | 5.1 / 10.6 |
| sharee | head (first chunks), 2 per source | 39 | 1.000 | 1.000 | 1.000 | 884 / 1763 | 5.3 / 16.2 |
| guest | best, 2 per source | 21 | 1.000 | 1.000 | 1.000 | 930 / 1656 | 4.3 / 9.8 |
| guest | best, 1 per source | 21 | 1.000 | 1.000 | 1.000 | 922 / 1579 | 4.5 / 10.5 |
| guest | head (first chunks), 2 per source | 21 | 1.000 | 1.000 | 1.000 | 930 / 1656 | 3.9 / 8.7 |
