# OQ protocol — PLM (template)

Execute on the installed system with test accounts: A (Admin), E1 and E2 (Engineering), Q (Quality),
P (Production). Record screenshots or exports as evidence. Each step references an SRS ID.

| # | SRS | Step | Expected | Result | Evidence | Initials |
|---|---|---|---|---|---|---|
| OQ-1 | AUTH-002/003 | Log in with a wrong password 5×, then the correct one | Generic error; then locked; events in audit trail | | | |
| OQ-2 | RBAC-003 | As A, open a part Under Review | No signing option; API refuses (403) | | | |
| OQ-3 | ITEM-001/008 | E1 creates a part and submits; E2 signs Eng Approved (a wrong password is refused first); Q signs Quality Approved, then Released | Status Released; 3 signatures with name, time, meaning, hash | | | |
| OQ-4 | RBAC-004 | E1 attempts to approve own revision | Refused (separation of duties) | | | |
| OQ-5 | ITEM-002/005 | Try to edit the released revision; create rev B, change value, release it | Edit impossible; A → Superseded, history intact | | | |
| OQ-6 | ITEM-006 | Q rejects a revision without a comment, then with one | First refused; then returned to Draft | | | |
| OQ-7 | INV-001/002 | Try to receive an unreleased part; receive a released part without MPN | Both refused with clear messages | | | |
| OQ-8 | INV-003 | Receive a lot; try to issue it before inspection | Refused; after Q signs Material Released, issue works | | | |
| OQ-9 | INV-004/005 | Quarantine a lot; try issue and reserve; P tries release; Q releases with disposition | Refused / refused / 403 / Available | | | |
| OQ-10 | INV-006/009 | Issue more than on hand; reserve most of the stock and issue beyond the free quantity | Refused both | | | |
| OQ-11 | INV-010 | Correct a mistaken issue with an adjustment referencing its # | New linked transaction; original unchanged | | | |
| OQ-12 | INV-011/012 | Receive a lot with a past expiry; set a part Prohibited | Issues refused, reasons shown | | | |
| OQ-13 | FILE-001/002 | Upload a PDF datasheet and download it (compare SHA-256); upload a .exe and a renamed HTML-as-PDF | Hash matches; both rejected | | | |
| OQ-14 | AUD-003 | Edit a draft field; open History | Before/after, user, time shown | | | |
| OQ-15 | AUD-004 | Audit trail → Verify audit chain; `verify-files`; `verify-inventory` | All intact | | | |
| OQ-16 | AUD-001 | (IT, witnessed) as `qplm_app` in psql: `UPDATE audit_event …`, `DELETE FROM stock_txn …` | Permission denied / append-only error | | | |
| OQ-17 | — | Print a location label; scan it with a phone | Opens the correct location after sign-in | | | |
| OQ-18 | AUD-002 | Export audit CSV with filters | File contains filter header; export appears in audit trail | | | |

## OQ-TRC — procurement and production genealogy

1. Create and electronically approve a supplier; verify unauthorised roles cannot approve it.
2. Create and sign a PO; receive a partial quantity and verify receipt→lot provenance. Attempt over-receipt and expect rejection.
3. Create a BOM revision, preview a KiCad CSV, release the BOM, then attempt direct and API mutation of released content and expect rejection.
4. Verify buildability excludes quarantined/expired/reserved material. Verify costing does not total mixed currencies.
5. Create a build from the released BOM. Attempt a build from a Draft BOM and expect rejection.
6. Attempt to issue a lot for the wrong item to a BOM line and expect rejection. Issue correct lots and verify stock-ledger correlation.
7. Attempt completion while short and expect rejection. Complete and electronically release after all requirements are satisfied.
8. Create finished serials, verify uniqueness/build quantity limits, and release a serial.
9. From that serial, retrieve BOM revision and consumed lots. From each consumed lot, retrieve all affected builds and serials.
10. Verify audit events/signatures and run the audit-chain integrity check.

## OQ-DOC — Controlled documents
1. Create `SOP-TEST-001` Rev 01 as Draft and verify it appears in the register with the entered metadata.
2. Attempt review/release without a file; verify the operation is rejected.
3. Upload a controlled file; verify filename and SHA-256 are displayed and the upload is audited.
4. Submit for review; verify Draft → In Review is recorded.
5. Attempt release using a user without `sign:document_released`; verify access is denied.
6. Release with an authorized user and re-entered password; verify status Released, effective/review/retention dates, content hash and signature attribution.
7. Attempt to replace the released file; verify the operation is rejected.
8. Create Rev 02; verify Rev 01 remains Released while Rev 02 is Draft/In Review.
9. Release Rev 02; verify Rev 02 becomes Released and Rev 01 becomes Superseded and remains downloadable.
10. Obsolete the document with an authorized signature and mandatory reason; verify the released revision becomes Obsolete and history remains retrievable.
11. Verify audit-chain and file-integrity checks after the sequence.
