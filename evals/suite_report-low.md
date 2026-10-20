# Eval suite (profile low)

All checks passed.

| check | result | seconds | report |
|---|---|---|---|
| unit tests | PASS | 10 | - |
| leak and PII test, every user x every question (no LLM) | PASS | 13 | suite-low/leaks.md |
| finder: leaks, denial format, retrieval accuracy | PASS | 2 | suite-low/finder.md |
| retriever: PII-free context, answer in context | PASS | 3 | suite-low/retriever.md |
| expert: real prompts scanned for leaks and PII, answer quality | PASS | 227 | suite-low/expert.md |
