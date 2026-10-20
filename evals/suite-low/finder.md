# Finder benchmark

config: Config(max_sources=5, ratio=0.95, min_score=0.8, K=3, N=2, min_denial_score=0.8, lex_weight=0.3, denial_mode='best', margin=0.04, tuned_for='snowflake-arctic-embed:33m')

87 questions + 35 unanswerable + 24 general-information; zero permission leaks (asserted).

| persona (roles) | readable q | found | hit@1 | MRR | opened before right | sources/q | restricted q | notice recall | wrong drive | extra notice | unknown-event empty | off-topic empty | notice on unanswerable | notice on general (association / event) | general answer found |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| superuser (test.board) | 87 | 0.98 | 0.92 | 0.94 | 0.08 | 1.34 | 0 | - | - | 0.00 | 0.96 | 1.00 | 0.00 | 0.00 / 0.00 | 0.67 |
| member (test.committee_member) | 26 | 0.96 | 0.92 | 0.94 | 0.04 | 1.19 | 61 | 0.85 | 0.00 | 0.00 | 0.96 | 1.00 | 0.00 | 0.00 / 0.00 | 0.67 |
| leader (test.leader) | 60 | 0.97 | 0.90 | 0.93 | 0.10 | 1.35 | 27 | 0.93 | 0.00 | 0.00 | 0.96 | 1.00 | 0.00 | 0.00 / 0.00 | 0.67 |
| other_leader (test.leader) | 61 | 0.97 | 0.93 | 0.95 | 0.03 | 1.15 | 26 | 0.73 | 0.00 | 0.00 | 0.96 | 1.00 | 0.00 | 0.00 / 0.00 | 0.67 |
| sharee (test.committee_member) | 39 | 0.97 | 0.92 | 0.95 | 0.05 | 1.23 | 48 | 0.85 | 0.00 | 0.00 | 0.96 | 1.00 | 0.00 | 0.00 / 0.00 | 0.67 |
| guest (none) | 21 | 0.95 | 0.90 | 0.93 | 0.05 | 1.14 | 66 | 0.86 | 0.00 | 0.00 | 0.96 | 1.00 | 0.00 | 0.00 / 0.00 | 0.67 |

latency: query embedding 13 ms mean (146 unique questions), ranking 0.1 ms mean / 0.2 ms p95 over 876 searches

superuser found: aligned 1.00, cross-topic 0.88
