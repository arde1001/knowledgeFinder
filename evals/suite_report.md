# Eval suite (profile high)

All checks passed.

| check | result | seconds | report |
|---|---|---|---|
| unit tests | PASS | 16 | - |
| leak and PII test, every user x every question (no LLM) | PASS | 13 | suite/leaks.md |
| finder: leaks, denial format, retrieval accuracy | PASS | 3 | suite/finder.md |
| retriever: PII-free context, answer in context | PASS | 3 | suite/retriever.md |
| expert: real prompts scanned for leaks and PII, answer quality | PASS | 201 | suite/expert.md |
