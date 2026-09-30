# Part planning and supporting files

On a part's **Details** tab, select **Edit minimum stock**. Enter a non-negative
quantity and a reason, then save. This changes the part's planning setting across
all revisions and records an audit event without creating a revision or altering
existing approvals. Requires `item:write`.

On **Files**, use the uploader under **Part files** to attach supporting files at
any lifecycle state. These files are shared across revisions and their uploads are
audited. Requires `files:upload`; normal file type, size and hash checks apply.
Existing signed **Revision files** remain frozen; draft revision uploads continue
to work. Part files do not form part of a signed revision's approved content.

The dashboard's **Below minimum stock** count uses available stock strictly less
than the minimum. A part with zero available stock and a zero minimum is excluded.
The separate out-of-stock metric remains independent of minimum stock.

Rebuild and deploy API and gateway together. No new database migration is required
for these changes.

## PCB manufacturing and project files

Upload a `.zip` bundle through **Files → Part files** and choose `gerbers` or
`kicad_project` as the Kind. Archives are stored intact without extraction, with
the normal upload size limit and SHA-256 verification. Draft revision files also
accept ZIP bundles when the archive should belong to a controlled revision.
