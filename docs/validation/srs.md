# Software Requirements Specification — PLM 0.1.0 (starter)

Status: **starter document**. Your organisation must review, amend and approve it under its own document control
before use in validation. Requirement IDs are referenced by automated tests (`@pytest.mark.req`) and by
`trace-matrix.md`. Tags: [SW] implemented by the software; [ORG] requires an organisational procedure.

## Scope
Release 0.1.0 covers: authentication, role-based access, electronic signatures, audit trail, controlled part
records and revisions, approved manufacturer list, storage locations and labels, lot-based inventory with an
append-only ledger, controlled file storage, backup/restore tooling. Other modules are out of scope (see README).

## Requirements

| ID | Requirement |
|---|---|
| SRS-AUTH-001 | Users must authenticate with a unique username and password; sessions can be ended by the user. [SW] |
| SRS-AUTH-002 | Failed login attempts are rejected with a generic message and recorded in the audit trail. [SW] |
| SRS-AUTH-003 | An account is locked for a configurable period after a configurable number of consecutive failures. [SW] |
| SRS-AUTH-004 | State-changing requests require a valid anti-CSRF token bound to the session. [SW] |
| SRS-AUTH-005 | All data and functions except health/version require an authenticated session. [SW] |
| SRS-RBAC-001 | Users can perform only actions permitted by their assigned roles. [SW] |
| SRS-RBAC-002 | Only users holding the specific signing authority may apply a given signature meaning. [SW] |
| SRS-RBAC-003 | The Administrator role has no signing authority by default. [SW] |
| SRS-RBAC-004 | The author of a revision cannot approve or release it (separation of duties). [SW] |
| SRS-RBAC-005 | Users cannot change their own role assignments; role changes are audited and end the user's sessions. [SW] |
| SRS-ITEM-001 | A revision is released only after Engineering and Quality approval signatures and a Release signature, each recorded with signer, time, meaning and content hash. [SW] |
| SRS-ITEM-002 | A revision that has left Draft cannot be edited through the application. [SW] |
| SRS-ITEM-003 | Content of a revision that has left Draft cannot be altered even by direct database access with the application's credentials. [SW] |
| SRS-ITEM-004 | Controlled records cannot be deleted. [SW] |
| SRS-ITEM-005 | Changes are made by new revisions; releasing a new revision supersedes the previous one and preserves its history. [SW] |
| SRS-ITEM-006 | Rejection returns a revision to Draft and requires a comment. [SW] |
| SRS-ITEM-007 | A signature is refused if the content the signer reviewed differs from the current content. [SW] |
| SRS-ITEM-008 | Applying a signature requires re-entry of the signer's password. [SW] |
| SRS-INV-001 | Stock can only be received against an item with a released, non-prohibited, non-obsolete revision. [SW] |
| SRS-INV-002 | Where an item has approved manufacturer sources, received stock must reference one of them. [SW] |
| SRS-INV-003 | Received lots are unusable until incoming inspection is signed. [SW] |
| SRS-INV-004 | Quarantined lots cannot be issued or reserved; release from quarantine requires a Material Released signature with a disposition comment. [SW] |
| SRS-INV-005 | Stock held in a quarantine location cannot be issued. [SW] |
| SRS-INV-006 | The application rejects movements that would make stock negative. [SW] |
| SRS-INV-007 | The database rejects negative balances regardless of the application. [SW] |
| SRS-INV-008 | Concurrent movements never overdraw a lot. [SW] |
| SRS-INV-009 | Reserved stock cannot be issued to other uses. [SW] |
| SRS-INV-010 | The inventory ledger is append-only; corrections are separate transactions referencing the original. [SW] |
| SRS-INV-011 | Expired lots cannot be issued. [SW] |
| SRS-INV-012 | Stock of a prohibited part cannot be issued. [SW] |
| SRS-AUD-001 | Audit events cannot be modified or deleted by the application's database role. [SW] |
| SRS-AUD-002 | No application function modifies or deletes audit events. [SW] |
| SRS-AUD-003 | Changes to controlled records are audited with user, time, action, and before/after values. [SW] |
| SRS-AUD-004 | Tampering with audit events by a privileged database user is detectable by chain verification. [SW] |
| SRS-FILE-001 | Stored files are identified by SHA-256; downloads return exactly the stored content. [SW] |
| SRS-FILE-002 | Disallowed file types and files whose content does not match their extension are rejected. [SW] |
| SRS-FILE-003 | Files cannot be added to a revision that has left Draft. [SW] |
| SRS-FILE-004 | Integrity verification detects missing or modified stored files. [SW] |
| SRS-SYS-001 | Database migrations apply, roll back and re-apply cleanly; the application refuses to start on a schema mismatch. [SW] |
| SRS-ORG-001 | Backups are taken on a defined schedule, stored off-host, and restores are periodically tested. [ORG] |
| SRS-ORG-002 | User access is reviewed periodically; accounts of leavers are deactivated promptly. [ORG] |
| SRS-ORG-003 | The server clock is synchronised to a trusted time source (NTP). [ORG] |
| SRS-ORG-004 | The system is validated for its intended use before use for regulated records. [ORG] |

## 0.2 controlled traceability requirements

- **SRS-TRC-001** The system shall maintain approved supplier master records with attributable electronic approval.
- **SRS-TRC-002** The system shall maintain controlled purchase orders with item, quantity, currency and unit-cost lines and prevent receipt beyond ordered quantity.
- **SRS-TRC-003** Goods receipt shall create component lots and retain the relationship to the PO and receipt record without rewriting the stock ledger.
- **SRS-TRC-004** BOMs shall be revision controlled; a released BOM revision and its lines shall be immutable at database level.
- **SRS-TRC-005** KiCad/generic CSV import shall preview resolved and unresolved internal part numbers before controlled creation.
- **SRS-TRC-006** Buildability shall exclude unavailable, quarantined, expired, reserved and prohibited material.
- **SRS-TRC-007** BOM costing shall retain currency context and shall not silently total mixed currencies.
- **SRS-TRC-008** A production build shall reference exactly one Released BOM revision.
- **SRS-TRC-009** Material issued to a build shall reference the exact BOM line, inventory lot, location and append-only stock transaction.
- **SRS-TRC-010** Build completion shall be blocked until each non-DNP BOM requirement is satisfied for the build quantity.
- **SRS-TRC-011** Build release shall require re-authenticated electronic signature and freeze build genealogy against subsequent mutation.
- **SRS-TRC-012** Finished serial numbers shall be unique and traceable to one production build; serial count shall not exceed build quantity.
- **SRS-TRC-013** Serial genealogy shall resolve backwards to the exact released BOM revision and actual component lots consumed.
- **SRS-TRC-014** Lot where-used shall resolve forwards to every production build and finished serial associated with that lot.
- **SRS-TRC-015** Controlled 0.2 state transitions and material transactions shall create audit evidence in the same database transaction as the change.

## Controlled document management — v0.3.0
- **SRS-DOC-001** The system shall maintain a searchable controlled document register with unique document number, title, type, owner, source, product/project, retention period and review interval.
- **SRS-DOC-002** The system shall retain revision history and identify revision, status, change summary, preparer, controlled filename, file SHA-256, effective date, review due date and retention date.
- **SRS-DOC-003** Only Draft revisions may have their controlled file set/replaced; Released, Superseded and Obsolete revision files shall not be replaceable through the application workflow.
- **SRS-DOC-004** A revision shall require a controlled file before it can enter review or release.
- **SRS-DOC-005** Release shall require authorized electronic signature with password re-authentication and shall bind the signature to a hash incorporating controlled metadata and the exact file SHA-256.
- **SRS-DOC-006** Releasing a new revision shall retain the prior released revision and mark it Superseded; creating a draft alone shall not remove the prior release from current use.
- **SRS-DOC-007** Obsolescence shall require authorized electronic signature and a reason; historical revisions shall remain retrievable.
- **SRS-DOC-008** Controlled-document changes, state transitions, signatures, uploads/replacements and downloads shall be attributable/auditable as applicable.
- **SRS-DOC-009** The system shall distinguish internal and external controlled documents and allow an external reference/publisher identifier.
- **SRS-DOC-010** Access to view, create/change, upload, release and obsolete documents shall be permission controlled.
