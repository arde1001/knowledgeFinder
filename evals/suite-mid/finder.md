# Finder benchmark

config: Config(max_sources=5, ratio=0.95, min_score=0.87, K=3, N=2, min_denial_score=0.87, lex_weight=0.3, denial_mode='best', margin=0.04, tuned_for='nomic-embed-text')

87 questions + 35 unanswerable + 24 general-information; zero permission leaks (asserted).

| persona (roles) | readable q | found | hit@1 | MRR | opened before right | sources/q | restricted q | notice recall | wrong drive | extra notice | unknown-event empty | off-topic empty | notice on unanswerable | notice on general (association / event) | general answer found |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| superuser (test.board) | 87 | 0.99 | 0.94 | 0.96 | 0.07 | 1.25 | 0 | - | - | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 / 0.00 | 0.75 |
| member (test.committee_member) | 26 | 1.00 | 0.96 | 0.98 | 0.04 | 1.19 | 61 | 0.87 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 / 0.00 | 0.75 |
| leader (test.leader) | 60 | 0.98 | 0.93 | 0.96 | 0.07 | 1.23 | 27 | 0.89 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 / 0.00 | 0.75 |
| other_leader (test.leader) | 61 | 0.98 | 0.97 | 0.98 | 0.02 | 1.15 | 26 | 0.77 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 / 0.00 | 0.75 |
| sharee (test.committee_member) | 39 | 1.00 | 0.95 | 0.97 | 0.05 | 1.18 | 48 | 0.88 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 / 0.00 | 0.75 |
| guest (none) | 21 | 1.00 | 0.95 | 0.98 | 0.05 | 1.19 | 66 | 0.88 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 / 0.00 | 0.75 |

latency: query embedding 13 ms mean (146 unique questions), ranking 0.1 ms mean / 0.3 ms p95 over 876 searches

superuser found: aligned 1.00, cross-topic 0.94
