# 01 — Requirements Analysis, Challenges and Assumptions

Status: DRAFT (Phase 0 design baseline) — requires review and approval by the organisation before use as a design input.

Working name: **PLM** (Quality PLM). Rename freely.

## 1. Classification convention used in all design documents

Every regulatory statement is tagged:

| Tag | Meaning |
|-----|---------|
| **[STD]** | Requirement of ISO 13485:2016 (clause cited) |
| **[SW]** | Software feature that helps satisfy a requirement |
| **[ORG]** | Organisational procedure/control that must exist outside the software |
| **[REC]** | Design recommendation (not a requirement of the standard) |
| **[EXT]** | Requirement of another regulation that applies only if in scope (e.g. 21 CFR Part 11) |

## 2. Requirement analysis summary

The specification describes six coupled subsystems:

1. **Controlled-record engine** — revisions, state machines, electronic approvals, audit. Every other module depends on it. It is built first and built once.
2. **Engineering data** — items (parts, PCBs, assemblies, products), AML, BOMs, CAD/documents, change control.
3. **Supply chain** — suppliers, supplier parts, prices, purchase orders, receiving, incoming inspection.
4. **Inventory** — locations, lots, ledger, reservations, quarantine/NCR.
5. **Manufacturing** — builds, as-built configuration, material issue, serials, genealogy, release.
6. **Platform** — auth, RBAC, files, search, reports, QR/labels, backup, versioning, validation evidence.

The hard problems are not the CRUD screens. They are:

- immutability of released revisions while still allowing controlled change;
- a stock ledger that cannot go negative under concurrency and can be rebuilt from history;
- genealogy that survives lot splits, transfers, returns and rework;
- signatures cryptographically/structurally bound to the exact content signed;
- an audit trail that is tamper-evident even against privileged users.

## 3. Challenges to the specification (proposed deviations)

Per §37 of the brief, these are cases where a literal implementation would create a quality, traceability or maintainability problem. Each is a proposal; none is final until accepted.

| # | Spec says | Problem | Proposal | Trade-off |
|---|-----------|---------|----------|-----------|
| C1 | Fixed hierarchy Product → Assembly → PCB → BOM → BOM Revision → Lines | Real products are multi-level and irregular (cable assemblies, enclosures, sub-PCBAs, firmware, kits). A fixed hierarchy breaks on the first exception. | **Unified item master** (`item` with class: component, bare PCB, PCBA, mechanical, cable, firmware, assembly, product) and **multi-level BOM**: a BOM is the child list of an assembly-type item revision. "PCB rev B, BOM rev C" becomes bare-PCB item rev B, PCBA item rev C. | Users must learn that a BOM revision *is* the PCBA/assembly revision. This is standard PLM practice and removes an entire class of inconsistency. |
| C2 | Reservation / reservation release as inventory transactions | Reservations do not change physical quantity. Mixing them with on-hand movements corrupts valuation and the "previous/resulting quantity" semantics. | Ledger carries **two quantity dimensions** (on-hand delta, reserved delta). Reservation rows have on-hand delta = 0. Constraint: `0 ≤ reserved ≤ on_hand`. | Slightly more complex ledger; much simpler invariants. |
| C3 | Previous / transaction / resulting quantity per transaction | Correct only if computed under a lock; otherwise concurrent transactions record wrong "previous" values. | Balance row locked (`SELECT … FOR UPDATE`) inside the transaction; ledger row stores before/delta/after with a DB check `after = before + delta`. Balances are a **projection** that a verification job rebuilds from the ledger and compares. | None material. |
| C4 | Partial quarantine of a lot | A lot-level status cannot represent "3 of 10 reels damaged". | Add **SPLIT** transaction: child lot inherits all provenance and `parent_lot_id`; the child is quarantined. Genealogy follows split chains. | One extra transaction type. |
| C5 | Alternates respected in buildability | Stock should pool at the internal part number, not per MPN. | By definition alternates are form-fit-function equivalent under one internal part number, so stock pools automatically. A BOM line may **restrict** the allowed AML entries (e.g. validated-only MPN for a critical position). Non-FFF-equivalent parts must be separate internal part numbers. | Requires engineering discipline on part-number creation; enforced by review, not software. |
| C6 | AML changes traceable | If AML lives inside the part revision, adding an alternate forces a part revision and ripples through BOMs. | **AML entries are individually controlled objects** with their own approval signatures and history. Part revision unaffected. | AML approval is a separate workflow; configurable to require an ECO. |
| C7 | BOM lines + exact released BOM in builds | Pinning child *revisions* in every BOM line causes revision ripple (every child change revises every parent). | BOM lines reference the child **item**; release requires each child to have a released revision. At build creation the **as-planned configuration is frozen** (exact child revisions resolved and stored). As-built records what was actually issued. | Standard "item-referenced BOM + frozen build configuration" pattern. Documented and validated as such. |
| C8 | "Approved" as a lifecycle state across record types | Different record types need different state machines (documents: Effective/Superseded; lots: Available/Quarantined). | One state-machine engine, per-type state definitions and transition rules held in code (not user-editable), with configurable *signature requirements* per transition. | State machines change only by software change control — deliberate. |
| C9 | Administrators must not approve | Correct, but a PostgreSQL superuser or host root can bypass every application control. | Application: separation of duties enforced. Database: application runs under least-privilege roles; audit table append-only with hash chain → **tamper-evident**, not tamper-proof. Host/DB superuser access is controlled **[ORG]**. | Honest limit; must be stated in validation documents. |
| C10 | CAD previews for KiCad symbols/footprints | Reimplementing KiCad rendering is error-prone. | Render with `kicad-cli` (sym/fp export svg) in an **optional preview worker** image. Previews are derived, non-controlled, cached against the source SHA-256. Downloaded files are always the controlled original. | Larger optional container (KiCad install). Fallback: "preview unavailable", download still works. |
| C11 | CAD library | A web library is only useful if KiCad consumes it. | **[REC]** Expose released parts through a read-only DB view for **KiCad database libraries** (ODBC, KiCad 7+), and an export of released symbol/footprint libraries as a versioned, hashed package. (KiCad HTTP libraries to be evaluated in Phase 3.) | ODBC setup on workstations; documented. |
| C12 | Celery/Redis implied by background work | Extra component to secure, back up and validate. | **PostgreSQL-backed job queue** (`SKIP LOCKED`) + one worker container. | Lower throughput than Redis; irrelevant at this scale. |
| C13 | Async FastAPI | Async SQLAlchemy complicates row locking and transaction scope. | **Synchronous SQLAlchemy 2.0 + psycopg 3** in FastAPI's threadpool. Explicit transaction per request/service call. | Marginally lower concurrency ceiling; far simpler correctness reasoning. |
| C14 | Hard deletion of drafts | Even drafts can be evidence (e.g. rejected change attempts). | No hard delete of any record through the application. Drafts may be **Discarded** (terminal state, audited). | Database grows; negligible. |
| C15 | Online price/part APIs | Conflicts with on-prem/no-cloud requirement. | Excluded. Optional future connector that only *proposes* data into a draft, never writes controlled data. | Manual price entry. |
| C16 | "Validation documentation" generated by this project | The code is AI-assisted custom software (GAMP 5 Category 5 equivalent). Tests passing ≠ fitness for intended use. | Supplier-side documentation (SRS, design, tests, trace matrix) is delivered here. **Independent code review by competent staff is recommended before IQ/OQ [REC]**; URS approval, risk acceptance, IQ/OQ/PQ execution and the validation report are the organisation's **[STD 4.1.6] [ORG]**. | Real effort on your side; unavoidable. |

## 4. Ambiguities and documented assumptions

| # | Ambiguity | Assumption (change if wrong) | Impact if wrong |
|---|-----------|------------------------------|-----------------|
| A1 | Target markets | UK/EU. FDA possible later. System implements Part 11-style e-signature controls anyway (low extra cost) **[EXT]**. | If US: FDA QMSR (ISO 13485 by reference) + Part 11 apply to FDA-required records; design already accommodates. |
| A2 | Device class / implantables | Not implantable. Build-level lot genealogy by default; per-serial / per-refdes genealogy optional per product. | ISO 13485 7.5.9.2 implantable traceability would make per-unit genealogy mandatory for those products. |
| A3 | NCR / CAPA | A minimal NCR (material/unit disposition) lives here. CAPA lives in the organisation's QMS; referenced by ID. | If CAPA must live here → additional module. |
| A4 | Units of measure | Quantities `NUMERIC(18,6)` with a UoM per item (pcs, m, g, ml). `pcs` enforced integral. No automatic UoM conversion; supplier pack-to-stock conversion factor on supplier part. | — |
| A5 | Sites | Multi-site capable (site is top location level); single legal entity. | Multi-entity would need org scoping on every table. |
| A6 | Currency | Every price carries ISO 4217 currency. No FX conversion by default. Costing shows per-currency subtotals and flags mixed-currency results as incomplete. Optional controlled FX table (rate, date, source, approver) applied explicitly. | — |
| A7 | Record retention | Configurable retention per record type; the application never destroys controlled records. Destruction, if ever, is an [ORG] procedure outside the app. | — |
| A8 | Authentication | Local accounts (Argon2id), optional TOTP MFA. OIDC/LDAP in a later phase. | If AD/Entra mandatory from day one → move forward in roadmap. |
| A9 | Firmware | Firmware = item (class firmware) with released revision holding the binary + hash. No CI integration. | — |
| A10 | Contract manufacturers | In-house builds first. CM kitting modelled later as transfer to a CM virtual location. | — |
| A11 | Reservation granularity | Soft (part-level, planning) and hard (lot-level, kitting). Allocation proposes FEFO then FIFO. | — |
| A12 | Expired stock | Computed as blocked for allocation; nightly job raises alerts. No automatic quarantine transaction — Quality decides. | — |
| A13 | Locale | en-GB UI, ISO 8601, UTC stored (`timestamptz`), displayed in configured local time zone. DB server clock is the timestamp authority; host NTP is [ORG]. | — |
| A14 | Revision labels | Released revisions: letters per configurable scheme (default skip I, O, Q, S, X, Z per ASME Y14.35 convention). Pre-release iterations tracked as integer iteration within a draft. | Configurable per record type. |
| A15 | Moisture-sensitive devices | Not in initial scope. MSL + floor-life tracking recommended for Phase 5+ **[REC]**. | — |
| A16 | UDI | Serial record has optional UDI-DI/UDI-PI fields; no UDI database submission. | — |
