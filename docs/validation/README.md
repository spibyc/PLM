# Validation starter

These are templates. Your organisation owns validation: intended use, risk assessment, approval of protocols,
execution and records.

| File | Purpose |
|---|---|
| `srs.md` | Requirements with IDs (tests reference these) |
| `trace-matrix.md` | Generated requirement → test → result matrix |
| `iq-protocol.md` | Installation qualification template |
| `oq-protocol.md` | Operational qualification template |

Regenerate the matrix with results on the release you are qualifying:

```bash
cd backend && pytest --junitxml=../results.xml && cd ..
python3 scripts/trace_matrix.py --junit results.xml > docs/validation/trace-matrix.md
```

Performance qualification (PQ) depends on your processes and is not templated here. Typically it means running
real parts through receiving, inspection and issue for a defined period, with pre-agreed acceptance criteria.
