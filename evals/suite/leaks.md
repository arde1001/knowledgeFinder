# Leak and PII test (no LLM)

All assertions held: 21 users (19 test people, a superuser and a guest) x 146 questions = 3066 finder + retriever runs in 18 s.

- sources returned: 2425, passages built: 2798, runs with no passage: 1309, denial notices: 755
- every source and passage readable by its user and live; no planted PII value in any passage; no 40-character window of a passage that exists only in files the user cannot read; every notice has exactly drive, name and the labelled contact role; the account block lists only what the user may see.
