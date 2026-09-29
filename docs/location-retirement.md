# Location retirement and Unallocated stock

On a location detail page, **Delete location** requires a reason of at least three
non-whitespace characters and the `location:delete` permission. The migration grants
this permission to the existing ADMIN role; new installations include it in ADMIN.
Production's existing `location:write` permission does not grant deletion authority.

The action calls `POST /api/locations/{id}/retire`. In one database transaction it:

- Transfers every nonzero lot balance to the system Unallocated location using
  correlated `TRANSFER_OUT` / `TRANSFER_IN` ledger entries.
- Preserves on-hand and reserved quantities, lot status, and historical transactions.
- Sets the original location inactive and records its retirement timestamp.
- Records the actor, time, reason, original location details, quantities moved,
  destination, transaction IDs and correlations in the existing audit trail.

A failed operation rolls back all changes. Concurrent location/stock changes can
produce a `location_busy` conflict; retry after the other operation finishes.
Retired locations cannot receive further postings or be reactivated through PATCH.
Historical location details, codes, QR links and transaction records remain readable.

Locations with **any** child rows are blocked, including inactive children, to retain
the historical hierarchy. There is no recursive deletion or reparenting workflow in
this change. Consequently, retiring children does not by itself make their parent
eligible for retirement.

## Resolving Unallocated inventory

The Locations page has a separate **Unallocated stock** link. Open a listed lot,
choose **Move to another location**, select Unallocated as the source and a physical
location as the destination. Enter the total quantity and, when applicable, the
**Reserved quantity included**. Reserved quantities move with the stock; they are
not cancelled. The service rejects transfers that would overdraw either balance.

Unallocated is identified by a unique `system_key`, not by its display name. It is
created by the migration, protected from editing/retirement/child creation, and
excluded from ordinary physical-location lists and receipt selectors. It cannot
be issued or newly reserved for production and does not contribute to available
stock. Lot inspection/quarantine restrictions still apply when relocating it.

## Migration and deployment

Migration `0007_location_retirement` adds `system_key` and `retired_at`, permits the
migration-created location to have no human creator, creates Unallocated, and grants
the new ADMIN permission. Existing stock and historical transactions are untouched
by the migration. An existing physical location with code `UNALLOCATED` stops the
migration with an explicit collision error; it is never silently converted.
Downgrading is refused once retirement or Unallocated inventory has been used.

Use the existing backup procedure before an installation upgrade. From the repository:

```sh
sudo docker compose build api gateway
sudo docker compose run --rm migrate
sudo docker compose up -d --force-recreate api gateway
```

This does not remove database volumes. The existing SELinux mount flags and unrelated
Docker networks are unchanged. These deployment commands have not been run against
the local installation; Docker requires interactive sudo privileges in this session.

## Validation

Backend integration tests use a disposable PostgreSQL 16 cluster, never the running
installation. Relevant tests:

```sh
pytest -o addopts= -q tests/test_location_retirement.py tests/test_location_migration.py tests/test_inventory.py
```

Coverage includes empty and populated retirement, multiple lots, reserved quantities,
reallocation, pending/quarantined lots, ledger and audit verification, rollback after
posting failure, child/system protections, permission/reason enforcement, historical
retrieval, active-list filtering, and location/lot lock contention. The migration
is also tested across upgrade/downgrade/upgrade with an existing location and ADMIN role.

The frontend passes TypeScript and Vite production builds. Chromium checks with mocked
API responses cover light/dark confirmation dialogs, required reason, children and
permission controls, successful navigation, Unallocated access, runtime favicon,
OS theme/default and persisted override, and white labels in screen/print media.
The confirmation button is checked for at least 4.5:1 text contrast.

The complete backend suite has three pre-existing failures, reproduced independently
on unchanged HEAD: the `0002_traceability` downgrade deletes protected number sequences;
the permissions test expects ADMIN not to sign although ADMIN currently has every
permission; and the supplier genealogy test expects an older supplier response shape.
