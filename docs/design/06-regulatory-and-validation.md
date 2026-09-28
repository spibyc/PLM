# 06 — Regulatory Support Matrix and Validation Strategy

This system does not make an organisation ISO 13485 compliant or certified. It is a tool that, once validated for its intended use, can generate and control evidence for certain QMS processes. Clause references are to ISO 13485:2016. Summaries of clauses are paraphrased; consult the standard for the normative text.

## 1. Compliance-support matrix

| System feature | ISO 13485 process / clause supported | Evidence generated | Procedural controls still required outside the software |
|---|---|---|---|
| Software validation package, version display, schema check, change log | 4.1.6 — validation of QMS software before initial use and after changes, proportionate to risk **[STD]** | URS, SRS, risk assessment, trace matrix, IQ/OQ/PQ records, release history | Validation procedure; approval of URS & risk acceptance; execution of IQ/OQ/PQ; revalidation decisions on every upgrade |
| Document control (revisions, approvals, effective dates, superseded marking) | 4.2.4 — review/approval before issue, change identification, availability of current versions, prevention of unintended use of obsolete documents, retention of obsolete documents **[STD]** | Document revision history, signatures, effective dates, superseded status | Document control SOP; decision on which documents are managed here vs elsewhere; training on use |
| Record control (immutability, audit, backups, integrity checks, retention settings) | 4.2.5 — records legible, identifiable, retrievable; changes remain identifiable; retention per defined period **[STD]** | Audit trail, row history, hash chain, integrity-run records, backup verification records | Records control SOP; retention periods; backup schedule ownership; periodic restore tests |
| Item master, BOM, CAD/document links, design history links | 7.3.4 outputs, 7.3.10 design & development file (supports) **[STD]** | Released item/BOM revisions, links to specs, drawings, verification/validation records | Design & development procedure; design reviews; the DHF/design file structure is defined by the organisation |
| ECR/ECO with affected items, risk/verification/validation refs | 7.3.9 — control of design & development changes, including review of effect, verification/validation as appropriate, approval before implementation **[STD]** | ECO records, signatures, before/after revisions, dispositions | Change control procedure; risk management per ISO 14971 (the software stores a reference only) |
| Supplier records, approval states, evaluations, performance events | 7.4.1 — supplier evaluation & selection criteria, monitoring, re-evaluation, records **[STD]** | Supplier approval history, evaluations, receipt/NCR-based performance data | Supplier control procedure; criteria definition; audits; quality agreements |
| PO content, approvals, MPN/AML checks | 7.4.2 — purchasing information; adequacy of requirements before communication to supplier **[STD]** | Approved PO with signatures, line MPNs | Definition of purchasing requirements (specs, quality agreements, change-notification clauses) |
| Receiving, incoming inspection, CoC attachment, material release | 7.4.3 — verification of purchased product **[STD]** | Inspection records, CoC files with hashes, release signatures | Inspection plans and acceptance criteria; inspector competence (6.2) |
| Build records, frozen configuration, material issue, quantities manufactured/approved | 7.5.1 — production records per device/batch with traceability and quantities manufactured/approved for distribution; record verified and approved **[STD]** | Build record, as-planned/as-built config, lots consumed, release signature | Production procedures, work instructions, process validation (7.5.6) outside this system |
| Lot IDs, serials, labels/QR, location records, status | 7.5.8 — identification, product status identification (incl. returned product) **[STD]** | Lot/serial/status records, label outputs | Physical labelling practice; segregation of returned/quarantined product |
| Genealogy, where-used, forward/backward trace | 7.5.9.1 traceability per documented extent; 7.5.9.2 additional requirements for implantables **[STD]** | Genealogy queries/reports | Defining the extent of traceability per product; implantable-specific records if applicable |
| Expiry dates, storage locations, quarantine locations | 7.5.11 — preservation of product (including shelf-life where applicable) **[STD]** | Expiry, location and movement history | Storage/handling procedures, environmental controls, ESD/MSL controls |
| Test records linked to units/builds, release signatures | 8.2.6 — monitoring & measurement of product; release records identify the person authorising release **[STD]** | Test record links, unit/build release signatures | Test procedures; test equipment calibration (7.6) — not managed here |
| Quarantine, NCR, dispositions, concessions, rework status | 8.3 — control of nonconforming product; concession only where justified and regulatory requirements met, with identity of the authoriser; rework **[STD]** | NCR records, disposition signatures, concession references, quarantine transactions | NCR procedure; concession justification rules; rework instructions |
| NCR/ECR references to external CAPA | 8.5.2 / 8.5.3 corrective/preventive action (reference only) **[SW]** | Cross-references | CAPA procedure and system |
| Supplier performance / inventory / NCR reports | 8.4 — analysis of data (input) **[SW]** | Reports | Management review, trending |
| Roles, signing authority, SoD | 5.5.1 — defined responsibilities and authorities **[STD]** | Role and authority grant history | Documented responsibilities; training records (6.2) |
| E-signatures bound to content, re-auth, manifestation | Not specified by ISO 13485 **[EXT: 21 CFR Part 11 if FDA-required records]** / **[REC]** | Signature records | Signature policy (e.g. users acknowledge e-signature equivalence where Part 11 applies) |
| ALCOA+ design (attribution, DB timestamps, immutability) | Data integrity is not a named ISO 13485 clause; supports 4.2.5 **[REC]** | — | Data-integrity policy |

## 2. Validation strategy

### 2.1 Principles

- Intended-use driven: validate the functions the organisation actually uses, to the depth of their risk to product quality and patient safety (4.1.6 **[STD]**).
- Guidance used (not requirements): ISO/TR 80002-2:2017 (validation of software for medical device quality systems), GAMP 5 2nd ed. risk-based approach, FDA Computer Software Assurance guidance if US in scope.
- Categorisation: custom-developed application → highest validation rigour for high-risk functions.
- AI-assisted development: treat the codebase as requiring **independent review by competent personnel** before OQ **[REC]**.

### 2.2 Deliverables (location: `docs/validation/`)

| Document | Produced by | Approved by |
|----------|-------------|-------------|
| Intended Use Statement | Organisation (template supplied) | Organisation |
| URS (`URS-xxx` IDs) | Draft supplied; organisation edits | Organisation |
| SRS (`SRS-xxx`) | This project | Organisation review |
| Architecture & data dictionary | This project (generated from models + docs) | Organisation review |
| Software risk assessment (function → failure mode → effect on product/record → severity × likelihood → controls → verification) | Draft supplied | Organisation |
| Trace matrix URS → SRS → code module → automated/manual test | Generated from test markers (`@pytest.mark.req("SRS-042")`) | Organisation |
| Validation plan / protocol | Template | Organisation |
| IQ protocol (host, versions, image digests, config, schema head, health checks) | Script + template | Organisation executes |
| OQ protocol (functional scripts per SRS incl. negative cases) | Template + automated evidence export | Organisation executes |
| PQ / intended-use scenarios (receive → inspect → build → release → trace; ECO cycle; recall trace) | Template | Organisation executes |
| Validation report template, release checklist, backup/restore verification, software change-control procedure | Templates | Organisation |

### 2.3 Automated evidence

`make validation-evidence` runs the test suite against a release build and emits: test results (JUnit XML + HTML), app version/commit, schema head, image digests, trace matrix, and a SHA-256 manifest of the evidence bundle. Automated test results are **evidence inputs**; they do not constitute validation.

### 2.4 Change control of the software itself

Every release: change description, impact assessment on validated functions, regression suite, targeted OQ re-execution for affected SRS items, release approval, recorded in release history. Upgrades refuse to run against a DB whose schema head differs from the image's expected head.
