# Eval suite

All checks passed.

| check | result | seconds | report |
|---|---|---|---|
| unit tests | PASS | 11 | - |
| leak and PII test, every user x every question (no LLM) | PASS | 20 | suite/leaks.md |
| finder: leaks, denial format, retrieval accuracy | PASS | 2 | suite/finder.md |
| retriever: PII-free context, answer in context | PASS | 7 | suite/retriever.md |
| expert: real prompts scanned for leaks and PII, answer quality | PASS | 112 | suite/expert.md |
