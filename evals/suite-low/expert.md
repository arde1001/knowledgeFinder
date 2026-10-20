# Domain expert benchmark

Hard assertions on every prompt sent to the model: no planted PII, no text that only unreadable files contain, no denial details, and every notice is exactly the fixed wording.

| persona | readable q | answer correct | right file cited | restricted q | notice names the answer's drive | unanswerable q | refused | general q | cites an expected file | s per question (mean / p95) |
|---|---|---|---|---|---|---|---|---|---|---|
| superuser | 40 | 0.93 | 0.97 | 0 | - | 15 | 1.00 | 15 | 0.60 | 2.2 / 5.8 |
| member | 12 | 1.00 | 1.00 | 28 | 0.86 | 15 | 1.00 | 15 | 0.60 | 0.1 / 0.6 |
| leader | 28 | 0.93 | 0.93 | 12 | 0.92 | 15 | 1.00 | 15 | 0.60 | 0.2 / 0.5 |
| other_leader | 28 | 0.96 | 0.96 | 12 | 0.75 | 15 | 1.00 | 15 | 0.73 | 0.2 / 0.5 |
| sharee | 17 | 1.00 | 1.00 | 23 | 0.83 | 15 | 1.00 | 15 | 0.67 | 0.2 / 0.5 |
| guest | 10 | 1.00 | 1.00 | 30 | 0.90 | 15 | 1.00 | 15 | 0.60 | 0.1 / 0.7 |

Follow-ups (21 pairs, superuser): rewrite keeps the event name 0.52, follow-up answered correctly 0.62.

Examples:
- `And what is the approved budget for that event?` -> `And what is the approved budget for WH-4679-H?`
- `And what is the venue booking reference for that event?` -> `And what is the venue booking reference for the Autumn Hackathon 2025?`
- `And what is the venue booking reference for that event?` -> `And what is the venue booking reference for that event?`
- `And what is the deadline for that event sponsor report?` -> `And what is the deadline for the event sponsor report?`
