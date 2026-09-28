# 08 — Implementation Roadmap

Each phase ends with a runnable `docker compose up -d --build` increment, migrations, tests and updated SRS/trace entries. Features not yet built are absent from the UI or shown as clearly marked "Not yet implemented" — never as dead buttons.

| Phase | Scope | Exit criteria |
|-------|-------|---------------|
| **0** Design | This document set | Assumptions accepted/corrected by the organisation |
| **1** Platform foundation | Repo structure, Docker Compose (gateway :8081, api, worker, db), env config, DB roles, Alembic baseline, structlog, health/ready/version, schema-head check, users, sessions, CSRF, Argon2id, rate limiting, lockout, RBAC registry, audit service + hash chain + triggers, numbering service, job queue, CI (lint, type-check, tests, pip-audit), React shell (sidebar, breadcrumbs, auth, toasts, error handling, tables) | Login/logout; admin user bootstrap via CLI (no default password); permission and audit tests pass; audit UPDATE/DELETE blocked at DB level |
| **2** Controlled-record engine + documents | controlled_object/record/revision, state machines, approval rules, signing with re-auth + hash binding, SoD, signing authority, file store + upload validation, document classes, document control lifecycle, PDF/image preview, integrity job | Document can be drafted → reviewed → approved → effective → superseded; negative tests (edit locked revision, unauthorised signature, hash mismatch, self-approval) pass |
| **3** Part master, AML, CAD library | Items (component class), categories, manufacturers, MPNs, AML entries with approval, CAD bindings, KiCad symbol/footprint preview worker, STEP/WRL viewer, KiCad DB-library read-only view | Released component with pinned CAD revisions; AML approval traceable |
| **4** Suppliers, locations, labels | Suppliers, approvals, evaluations, supplier parts, price records; location hierarchy (ltree), QR tokens, label PDFs, scan landing pages (mobile layout) | Scan QR → location record on phone |
| **5** Inventory & quarantine | Lots, balances, ledger (all txn types incl. split/reversal), allocation eligibility, quarantine, NCR + dispositions, projection rebuild check | Concurrency stress test: no negative stock; quarantine blocks allocation |
| **6** Purchasing & receiving | PO lifecycle + amendments + thresholds, supplier/AML checks, receiving → lot creation, incoming inspection, CoC attachments | PO → receipt → inspected lot, fully traced |
| **7** Products, BOMs, costing | Assembly/PCBA/product items, multi-level BOM, refdes uniqueness, AML restrictions, KiCad BOM import with diff preview, release checks, buildability, reservations, costing (per-currency) | Released PCBA; "can we build 25?" correct against fixture data |
| **8** Builds, serials, genealogy | Builds with frozen config, kitting, issue/consume, returns, units, per-unit genealogy option, test records, release, forward/backward trace, where-used | Recall scenario: lot → all affected serials, and reverse |
| **9** Change control | ECR, ECO, affected items, dispositions, release guard, implementation tracking | Post-release change impossible without approved ECO |
| **10** Search, dashboard, reports | Global search (FTS + trigram), dashboard, report catalogue, CSV + PDF with required header/footer metadata, saved filters | Report metadata verified by test |
| **11** Backup/restore & ops | Backup container (pg_dump custom format + file manifest + config), verification (restore to scratch DB, row counts, hash check, chain verify), admin guide | Documented restore test passes end-to-end |
| **12** Validation package & hardening | URS/SRS finalisation, risk assessment, trace matrix generation, IQ/OQ/PQ protocols, validation report template, release checklist, security review, CSP tuning, accessibility pass, user/admin guides, sample data | Evidence bundle generated from a tagged release |

Optional later: OIDC/LDAP, S3 object-lock backend, CM kitting, MSL floor-life, UDI export, KiCad HTTP library, per-refdes genealogy UI.

## Delivery mechanics in this conversation

The full system is a large codebase; it will be delivered phase by phase across turns, each as a complete repository snapshot. Validation-relevant IDs (SRS numbers, test markers) are introduced from Phase 1 so traceability is built in, not retrofitted.
