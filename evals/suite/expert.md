# Domain expert benchmark

Hard assertions on every prompt sent to the model: no planted PII, no text that only unreadable files contain, no denial details, and every notice is exactly the fixed wording.

| persona | readable q | answer correct | right file cited | restricted q | notice names the answer's drive | unanswerable q | refused | general q | cites an expected file | s per question (mean / p95) |
|---|---|---|---|---|---|---|---|---|---|---|
| superuser | 10 | 1.00 | 1.00 | 0 | - | 15 | 1.00 | 15 | 0.73 | 0.5 / 2.2 |
| member | 4 | 1.00 | 1.00 | 6 | 1.00 | 15 | 1.00 | 15 | 0.73 | 0.4 / 1.4 |
| leader | 8 | 1.00 | 1.00 | 2 | 0.50 | 15 | 1.00 | 15 | 0.60 | 0.4 / 1.2 |
| other_leader | 7 | 0.86 | 0.86 | 3 | 0.67 | 15 | 1.00 | 15 | 0.67 | 0.4 / 1.0 |
| sharee | 3 | 1.00 | 1.00 | 7 | 0.86 | 15 | 1.00 | 15 | 0.73 | 0.4 / 2.2 |
| guest | 4 | 1.00 | 1.00 | 6 | 1.00 | 15 | 1.00 | 15 | 0.67 | 0.3 / 1.0 |

Follow-ups (8 pairs, superuser): rewrite keeps the event name 1.00, follow-up answered correctly 1.00.

Examples:
- `And what is the approved budget for that event?` -> `What is the approved budget for Alumni Homecoming 2026?`
- `And who is responsible for stage setup at that event?` -> `Who is responsible for stage setup at the Autumn Hackathon 2025?`
- `And who is responsible for first aid at that event?` -> `And who is responsible for first aid at Autumn Hackathon 2026?`
- `And what is the order number for the stage lighting supplied by BusLine North for that event?` -> `And what is the order number for the stage lighting supplied by BusLine North for Career Fair 2024?`
