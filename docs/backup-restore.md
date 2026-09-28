# Backup and restore

## Backup

```bash
scripts/backup.sh                 # writes ./backups/plm-<UTC timestamp>/
scripts/backup.sh /mnt/nas/plm   # or a chosen root
```

Each backup directory contains:

| File | Contents |
|---|---|
| `db.dump` | `pg_dump` custom format |
| `filestore.tar` | Controlled file store |
| `version.json` | Application and schema version |
| `audit-chain.json` | Audit chain verification result and chain head |
| `SHA256SUMS` | Hashes of all of the above |

The database is dumped before the files. Because files are write-once and stored before their records commit,
every file referenced in the dump is present in the archive. Online backup is safe; users can keep working.

Schedule it, for example nightly via cron: `15 2 * * * cd /opt/plm && scripts/backup.sh /mnt/backup/plm >> /var/log/qplm-backup.log 2>&1`.
Copy backups off-host, apply a retention policy set by your procedures, and keep the `audit-chain.json` head
values in a separate record.

## Restore

```bash
scripts/restore.sh backups/plm-20260928T021500Z
```

The script:
1. Verifies `SHA256SUMS` and asks you to type `RESTORE` to confirm.
2. Stops the app.
3. Recreates the database and restores the dump, including triggers and grants.
4. Replaces the file store.
5. Restarts the app.
6. Runs `verify-audit`, `verify-files` and `verify-inventory`, and exits non-zero on any failure.

Restore with the same application release the backup was taken with (see `version.json`), then upgrade if
needed.

## Restore testing

At least quarterly, and before go-live, restore the latest backup onto a separate host or a separate Compose
project (`docker compose -p qplm-restoretest …` with a different `HTTP_PORT`). Confirm all three verifications
pass, and spot-check a few records and file downloads. Record the date, backup ID, result and tester (SRS-ORG-001).
