# Changelog

## Unreleased

- Added ZIP attachments for PCB Gerber bundles and KiCad projects, with gerbers and kicad_project file kinds. Archives are stored intact and downloaded unchanged.

- Superusers can delete an unreferenced discarded revision with a reason and confirmation. Audit history remains intact; deletion of the last revision is blocked.

- Part details now allow audited minimum-stock changes without a new revision. The Files tab supports shared part attachments at any lifecycle state while preserving signed revision files.
- The dashboard counts only parts whose available stock is strictly below their minimum; zero stock with a zero minimum is excluded.

- Receive Stock and PO part selectors now show internal PN, approved MPNs and description. New POs support adding and removing multiple lines before creation.

- Receive Stock now selects matching PO lines, fills outstanding quantities, records linked goods receipts, and rejects stale or duplicate submissions. PO lines show receipt status, and received lots link back to their order.

- Fixed flashing part selectors in Edit PO by keeping selected labels stable across search results.

- Added purchase-order detail pages, linked from PO numbers in the register and opened after creation.
- PO details show supplier, dates, notes, line items, costs, receipt progress, linked lots and approval signatures; authorised users can approve Draft orders from the detail page.
- Added audited draft PO editing with multiple lines, add/remove controls, supplier and order metadata changes, revision conflict checks, and an approval lock.
- New PO and draft line editors fill Supplier part number from the selected part purchasing source's Source part number, preserving saved values until a replacement source is selected.

## 0.3.1 — Generic PLM branding and public-repository preparation

- Renamed the public application identity from QPLM to **PLM**.
- Removed organisation-specific names and artwork from the application and documentation.
- Added runtime `branding/branding.js` and `branding/logo.png`; deployments can change organisation name, tagline and logo without editing application source.
- Changed the default Compose project/image identity to `plm` for new installations while retaining legacy internal database identifiers for non-destructive upgrades.
- Renamed public environment configuration to the `PLM_` prefix.
- Expanded README with branding, deployment, persistence, document control, supplier/source relationships, upgrade and GitHub hygiene guidance.
- Added `SECURITY.md` and `CONTRIBUTING.md`, strengthened `.gitignore`, and removed generated Python/TypeScript cache files from the release.
- No database schema change; expected schema remains `0006_document_control`.

## 0.3.0 — Controlled document management

Adds an ISO 13485-oriented controlled document register and revision workflow:
- controlled document master/register with document number, title, type, owner, source, product/project, retention and review interval;
- Draft → In Review → Released lifecycle with password re-authenticated electronic release signature;
- release signature bound to a SHA-256 hash of controlled metadata and the exact content-addressed file;
- new revisions retain prior released revisions and automatically mark the prior release Superseded only when the new revision is released;
- obsolete workflow with signed reason; obsolete/superseded files remain retrievable;
- revision history records change summary, preparer, effective date, review due date, retention date, hashes and signatures;
- draft-only file replacement; released files cannot be replaced through the document API;
- internal/external document classification and external-reference field;
- document permissions and controlled migration of existing default roles;
- document downloads are audited;
- schema revision `0006_document_control`.

This functionality supports document/record controls expected by ISO 13485:2016, but software installation alone does not establish QMS conformity. the organisation must define and validate its procedures, responsibilities, retention periods, regulatory requirements and intended use.

## 0.2.3 — Supplier & workflow UI completion

- Added supplier creation directly from Purchasing → Suppliers.
- Added Draft supplier editing, electronically signed approval, suspension and reinstatement with mandatory reason and audit trail.
- Added purchase-order creation and electronically signed PO approval controls to the UI.
- Added BOM creation and electronically signed release controls to the UI.
- Added production-build creation from released BOM revisions.
- Added empty-state guidance and permission-aware action controls across traceability pages.
- Added supplier detail/update/status API endpoints and audit-backed state transitions.
- Added migration marker `0005_supplier_workflow` and corrected expected schema revision.
- Preserved released-record immutability, role permissions, electronic signatures and append-only audit records.

## 0.2.2 — the organisation document branding and distributor sources

- Aligns UI palette to the supplied the organisation document template (navy/slate/teal family) and uses the supplied the organisation mark in the application header.
- Adds first-class distributor purchasing sources beneath manufacturer parts: distributor, distributor part number, product URL and preferred flag.
- Manufacturer source proposal can capture an initial purchasing source; data model supports multiple distributor sources per manufacturer part.
- Fixes expected database schema revision for the release and adds migration 0004_distributor_sources.


## 0.2.0 — first runnable release
- Authentication, sessions, CSRF, lockout, per-IP login rate limit (per API worker).
- Roles and permissions; separation of duties; administrator without signing authority.
- Electronic signatures with re-authentication, meaning, review-cycle and content-hash binding.
- Hash-chained append-only audit trail; CSV export; chain verification (UI and CLI).
- Parts with controlled revisions, lifecycle states, supersession; approved manufacturer list.
- Controlled file store with SHA-256 identity, MIME validation and integrity verification.
- Storage location hierarchy, QR codes, printable labels, scan routes.
- Lot inventory with append-only ledger, signed incoming inspection and quarantine release.
- Database-level integrity controls and least-privilege application role.
- Docker Compose deployment; backup/restore scripts with post-restore verification.
- Validation starter: SRS, generated traceability matrix, IQ/OQ templates.
- Schema revision: `0001_initial`.

## 0.2.0 — Procurement-to-production traceability
- Controlled suppliers with electronic approval.
- Purchase orders, controlled receipts and lot provenance.
- Revision-controlled BOMs with signed/hash-bound release and KiCad CSV preview.
- Buildability and currency-aware latest-purchase costing.
- Production builds tied to exact released BOM revisions.
- Actual component-lot consumption tied to append-only stock transactions.
- Finished serials, backward genealogy and lot where-used.
- PostgreSQL guards for released BOM/build/serial genealogy.
- Extended permissions, SRS, risk analysis, traceability matrix, OQ and negative tests.
