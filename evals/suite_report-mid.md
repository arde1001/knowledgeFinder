# Eval suite (profile mid)

All checks passed.

| check | result | seconds | report |
|---|---|---|---|
| unit tests | PASS | 16 | - |
| leak and PII test, every user x every question (no LLM) | PASS | 12 | suite-mid/leaks.md |
| finder: leaks, denial format, retrieval accuracy | PASS | 2 | suite-mid/finder.md |
| retriever: PII-free context, answer in context | PASS | 3 | suite-mid/retriever.md |
| expert: real prompts scanned for leaks and PII, answer quality | PASS | 166 | suite-mid/expert.md |
