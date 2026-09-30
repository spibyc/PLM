# Deleting a discarded revision

As a superuser, open the part and select the discarded revision. Click
**Delete discarded revision**, enter a reason, and confirm. This removes only
the selected revision; the part and other revisions remain.

Only Discarded revisions can be deleted. Deletion is blocked for the last
remaining revision, the current released revision, or a revision referenced
by inventory or another revision. Database foreign keys protect other references.

Existing audit events, signatures, transitions and file evidence are retained.
The deletion and reason are recorded against both the part and revision;
the part's History tab includes the deletion event. Audit chains are not rewritten.

Deploy the API and gateway together. No new schema migration is required.
