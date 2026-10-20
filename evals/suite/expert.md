# Domain expert benchmark

Hard assertions on every prompt sent to the model: no planted PII, no text that only unreadable files contain, no denial details, and every notice is exactly the fixed wording.

| persona | readable q | answer correct | right file cited | restricted q | notice names the answer's drive | unanswerable q | refused | general q | cites an expected file | s per question (mean / p95) |
|---|---|---|---|---|---|---|---|---|---|---|
| superuser | 40 | 1.00 | 1.00 | 0 | - | 15 | 1.00 | 15 | 0.53 | 0.5 / 1.6 |
| member | 12 | 1.00 | 1.00 | 28 | 0.86 | 15 | 1.00 | 15 | 0.73 | 0.3 / 1.0 |
| leader | 28 | 1.00 | 1.00 | 12 | 0.92 | 15 | 1.00 | 15 | 0.60 | 0.4 / 1.1 |
| other_leader | 28 | 0.96 | 0.96 | 12 | 0.75 | 15 | 1.00 | 15 | 0.73 | 0.4 / 1.0 |
| sharee | 17 | 1.00 | 1.00 | 23 | 0.83 | 15 | 1.00 | 15 | 0.80 | 0.4 / 1.0 |
| guest | 10 | 1.00 | 1.00 | 30 | 0.90 | 15 | 1.00 | 15 | 0.73 | 0.3 / 0.8 |

Follow-ups (21 pairs, superuser): rewrite keeps the event name 1.00, follow-up answered correctly 1.00.

Examples:
- `And what is the approved budget for that event?` -> `What is the approved budget for Alumni Homecoming 2026?`
- `And what is the venue booking reference for that event?` -> `What is the venue booking reference for the Autumn Hackathon 2025?`
- `And what is the venue booking reference for that event?` -> `What is the venue booking reference for Autumn Hackathon 2026?`
- `And what is the deadline for that event sponsor report?` -> `What is the deadline for the Career Fair 2024 sponsor report?`
