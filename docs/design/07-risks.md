# 07 — Security and Data-Integrity Risks (initial register)

Severity (S) / Likelihood (L): H/M/L before controls. Full software risk assessment is produced in Phase 12 against the URS.

## 1. Data integrity

| ID | Hazard | S | L | Controls | Verification |
|----|--------|---|---|----------|--------------|
| DI-01 | Released BOM/item edited in place | H | M | Service check, DB trigger, content hash on signatures | Negative API + direct-SQL tests |
| DI-02 | Negative or inconsistent stock under concurrency | H | M | Row locks, CHECK constraints, before/after checks, projection rebuild job | Concurrent posting stress tests |
| DI-03 | Quarantined/expired/prohibited material allocated to build | H | M | Eligibility function used by all allocation paths; DB check on hard allocation | Negative tests per condition |
| DI-04 | Audit gaps (changes without events) | H | L | Same-transaction audit, row-history backstop, reconciliation job | Bypass test via raw SQL → finding raised |
| DI-05 | Audit tampering by privileged user | H | L | Append-only triggers, least-privilege roles, hash chain, external anchor | Chain-break detection test |
| DI-06 | Controlled file altered/lost on disk | H | L | Content addressing, 0440 perms, integrity job | Tamper test → HASH_MISMATCH |
| DI-07 | Signature applied to content different from what signer saw | H | L | Client-shown hash compared server-side at signing | Race test |
| DI-08 | Genealogy broken by split/transfer/rework | H | M | Parent-lot links, correlation IDs, recursive trace tests | Genealogy scenario tests |
| DI-09 | Wrong timestamps (client clock) | M | M | DB clock only; host NTP [ORG] | Test that client timestamps are ignored |
| DI-10 | Mixed-currency cost silently summed | M | M | Currency on every price, typed Money, per-currency totals | Unit tests |
| DI-11 | Schema/app mismatch after upgrade | H | L | Startup schema-head check; migrations tested up/down on fixture DB | Migration tests |
| DI-12 | Untested backup | H | M | Automated restore verification into scratch DB + file hash check | Backup/restore test |
| DI-13 | KiCad import introduces wrong parts | M | M | Preview/diff, unknown parts blocked, commit only into Draft | Import tests with malformed files |

## 2. Security

| ID | Threat | S | L | Controls |
|----|--------|---|---|----------|
| SE-01 | Credential stuffing / brute force | H | M | Argon2id, per-account and per-IP rate limits, lockout, optional MFA (recommended mandatory for signers) |
| SE-02 | Session hijack | H | L | HttpOnly/Secure/SameSite=Strict cookies, rotation on login and privilege change, idle + absolute timeout, HTTPS only in production |
| SE-03 | CSRF | H | M | Synchroniser token on unsafe methods |
| SE-04 | Privilege escalation / IDOR | H | M | Server-side permission checks on every route; object-scope checks; permission test matrix generated from registry |
| SE-05 | Malicious upload (polyglot, SVG/HTML script, zip bombs) | H | M | Extension allow-list, libmagic, size limit while streaming, no inline serving of active content, nosniff, archive handling disabled by default |
| SE-06 | Path traversal via filenames | H | L | Filenames never used as paths; content-addressed keys |
| SE-07 | SQL injection | H | L | ORM parameterisation; no string SQL; lint rule |
| SE-08 | XSS | H | M | React escaping, strict CSP (no inline script), sanitised previews |
| SE-09 | Secrets leakage | H | L | Env vars/Docker secrets, no defaults in production (startup refuses weak/missing secret), `.env` git-ignored |
| SE-10 | Admin approves quality records | H | L | Signing authority separate from roles; no self-grant |
| SE-11 | Supply-chain compromise of dependencies/images | M | M | Pinned versions + lockfiles, image digests, `pip-audit`/`npm audit` in CI, SBOM (CycloneDX) per release |
| SE-12 | Exposed DB port | H | L | DB on internal Docker network only |
| SE-13 | Log injection / sensitive data in logs | M | M | Structured logging, no passwords/tokens logged, redaction filter |
| SE-14 | DoS via expensive queries/reports | M | M | Pagination limits, timeouts, reports via job queue |
| SE-15 | Host compromise | H | L | Out of scope of app; hardened host, patching, firewall, backups off-host [ORG] |

## 0.2 risk controls

| Hazard / failure | Primary controls |
|---|---|
| Unapproved supplier material enters production | supplier approval state; controlled PO; incoming inspection; lot usability rules |
| Over-receipt masks purchasing discrepancy | row-locked PO line and quantity constraint/service check |
| Production uses wrong design definition | build FK to Released BOM revision; release immutability trigger |
| Wrong component lot issued to BOM line | service verifies lot item equals BOM-line item; stock usability checks |
| Insufficient material recorded as complete | completion sums persisted build-material issues against BOM × build quantity |
| Genealogy changed after release | DB triggers protect released BOM/build/serial and build-material records |
| Recall scope cannot be determined | indexed lot→build material→build→serial relationships and where-used API |
| Costing combines currencies incorrectly | currency surfaced per line; mixed-currency total suppressed |
