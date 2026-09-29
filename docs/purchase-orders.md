# Purchase orders

Open **Purchasing → Purchase orders**, then click a PO number to view its details.
Select **New PO** to create an order with one or more lines. Use **Add line** and
the individual **Remove line** buttons before saving. New orders open their detail
page after creation.

Part selectors in purchase orders and Receive Stock show **internal PN — MPN —
description**. Multiple approved MPNs are separated by slashes, with preferred
entries first; parts without one show **No approved MPN**.

While an order is Draft, users with `po:write` can select **Edit PO** to change the
supplier, currency, expected date, notes and order lines. Use **Add line** or the
individual **Remove line** buttons. At least one line is required. Saving requires
a reason and records the before/after values in the audit trail.

For each line, select a part and its purchasing source. **Supplier part number** is
copied from that source's **Source part number**, and the corresponding manufacturer
part is saved with the line. A single or uniquely preferred source with a part number
can populate a new empty selection automatically. Existing saved part numbers are
preserved until you select a replacement. If no purchasing sources exist for the
selection, manual entry is available. Purchasing source names are separate from the
approved supplier register: selecting a source does not change the PO supplier.

Users with `sign:po_approved` can approve an order after reviewing its lines. Approval
requires password reauthentication. Approved orders are read-only through the editing
API and UI; receiving stock continues through the existing receipt workflow.

Every draft save advances the PO revision. Stale edits and approvals sent with an
older revision are rejected; reopen the order to review the latest version. Editing
and approval lock the same PO row to prevent a save from racing with approval.

No new schema migration is required for PO editing; it uses the existing revision,
line and audit tables. Rebuild and deploy both API and gateway for these changes.

## Receiving against an order

On **Receive stock**, select the part, manufacturer source and supplier, then choose
**Purchase order reference**. The dropdown matches the part and supplier's registered
name or code (ignoring case and repeated spaces), and respects a specified manufacturer
part. Purchasing-source distributor names are not foreign keys to the supplier register;
use a matching supplier name or code to make the relationship unambiguous.

Choose a PO line to fill its outstanding quantity. Reduce that quantity for a partial
delivery. Draft, closed/cancelled and fully received lines cannot be selected. The
`po:receive` permission is required for linked receipts.

Receiving creates a goods receipt, increments that line's received quantity, and
updates the PO to Partially Received or Received. The PO detail page shows the status
of every line and the received lots; each linked lot also links back to its PO.
Repeated/stale submissions are rejected under the same order lock, including partial
receipts. After a failed linked receipt, review and reselect the refreshed PO line.
A later legitimate partial delivery can receive only the remaining balance.

Without a PO selection, receipt remains a standalone inventory operation and does not
change any PO balance. Changing part or supplier clears the prior PO selection and
quantity. No schema migration is needed for this workflow.
