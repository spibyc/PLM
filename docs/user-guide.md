# User guide

## Parts

**Create a part** (Engineering): Parts → New part. A part number (`PN-000123`) is assigned automatically and the
part starts as revision **A** in **Draft**. Edit the details, attach files (datasheet, KiCad symbol and
footprint, 3D model), then **Submit for review**. Submitting freezes the content and computes its content hash.

**Approve and release**: a revision needs an **Engineering Approved** and a **Quality Approved** signature from
people other than its author. It then becomes **Approved**, and a **Released for Production** signature makes it
the current revision. Any signer can instead sign **Rejected** with a comment, which returns it to Draft.

**Signing**: choose the meaning, re-enter your password, and add a comment where required. The dialog shows the
content hash you are signing. If someone changed the record after you opened it, the signature is refused;
reload and review again.

**Change a released part**: New revision → give a reason. The next revision letter (I, O, Q, S, X, Z are skipped)
is created as a Draft copy, including files. The released revision stays current until the new one is released,
at which point the old one becomes **Superseded**.

**Lifecycle**: Quality can mark a released revision **NRND**, **Obsolete** or **Prohibited** (Change lifecycle…,
comment required). Stock of prohibited or obsolete parts cannot be issued.

**Manufacturer sources** tab: propose a manufacturer and MPN; someone else with approval authority signs
**AML Approved**. Once a part has approved sources, receipts must name one of them.

## Stock

**Receive** (Production/Purchasing): Receive stock → part, approved MPN, quantity, location, and supplier, PO,
lot and date code details. This creates lot `LOT-000123` in **Pending Inspection**. Upload the CoC on the lot
page.

**Inspect** (Quality): Record inspection… → sign **Material Released** (the lot becomes Available) or
**Material Rejected** (the lot becomes Quarantined, comment required).

**Stock actions** on a lot page:

| Action | Notes |
|---|---|
| Issue to production | Needs a reference (build or work order). Only Available, unexpired lots in normal locations. |
| Return to stock | Only up to what was issued from the lot |
| Reserve / Release reservation | Reserved stock cannot be issued for anything else |
| Move to another location | Reserved quantity cannot be moved |
| Post adjustment | Reason required. To correct a mistaken transaction, enter its # in "Corrects transaction". |
| Scrap | Reason required |
| Quarantine | Reason required (e.g. an NCR number). Releasing it needs a Quality signature with a disposition. |

Nothing in the ledger is ever edited. Mistakes are corrected with a new, linked transaction.

## Locations and labels

Locations nest site → room → cabinet → drawer → bin → compartment, and codes build up automatically
(`LAB-STORES-C01-D01-B01`). **Print labels** on a location page prints that location and everything directly
inside it on 62 × 29 mm labels (browser print, margins none, scale 100%). A lot page has a **Label** button.
Scanning a label with a phone camera opens the location or lot, after sign-in.

## Search and history

The top search bar finds part numbers, descriptions, values, MPNs, lot numbers, supplier and manufacturer lots,
PO references and location codes. Every part and lot has a **History** tab listing who changed what and when.
Quality can see the full **Audit trail**, export it to CSV (the export itself is audited) and verify the chain.
