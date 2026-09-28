# Administrator guide

## Roles

| Role | Can do | Signing authority |
|---|---|---|
| ADMIN | Manage users and roles, locations, view everything, verify files | **None** |
| ENGINEERING | Create parts, edit drafts, submit, propose manufacturer sources, upload files | Engineering Approved, Released for Production, AML Approved |
| QUALITY | Review, quarantine, adjust, verify, read audit trail | Quality Approved, Released for Production, lifecycle (NRND/Obsolete/Prohibited), Material Released/Rejected, AML Approved |
| PURCHASING | Receive stock, propose manufacturer sources | None |
| PRODUCTION | Receive, issue, return, reserve, transfer, adjust, scrap, quarantine, manage locations | None |
| READONLY | View parts, stock, locations | None |

A user can hold several roles. Separation of duties is enforced regardless of roles: the author of a revision
cannot approve or release it, and whoever proposes an AML entry cannot approve it. Administrators cannot change
their own roles; a second administrator must do it. Role changes end the affected user's sessions.

Default role permissions are created once by `bootstrap` and are not overwritten on upgrade. The full permission
list is shown under **Users & roles**. Changing role permissions is not available in the UI in 0.1.0. If your
procedures need a different split, change it under your own change control in SQL (table `role_permission`,
connected as the owner role) and record the change.

## Accounts

- Passwords: minimum 12 characters, mixed case, at least one digit (`PLM_PASSWORD_MIN_LENGTH`).
- Lockout: 5 consecutive failures lock the account for 15 minutes (`PLM_LOGIN_MAX_FAILURES`,
  `PLM_LOCKOUT_MINUTES`). An administrator password reset clears the lock.
- Sessions: 30 minutes idle and 12 hours absolute (`PLM_SESSION_IDLE_MINUTES`, `PLM_SESSION_ABSOLUTE_HOURS`).
- Users are never deleted, because they are referenced by records. Deactivate leavers; this also ends their sessions.

## Configuration (environment, set via `.env` → `docker-compose.yml`)

| Variable | Default | Purpose |
|---|---|---|
| `PUBLIC_BASE_URL` | `http://localhost:8081` | Encoded into QR labels. Set it before printing labels. |
| `COOKIE_SECURE` | `false` | Must be `true` behind HTTPS |
| `PLM_ENVIRONMENT` | `production` | `development` allows demo data |
| `SESSION_IDLE_MINUTES` | 30 | |
| `MAX_UPLOAD_MB` | 50 | The gateway limit is 60 MB; raise both together if needed |
| `HTTP_PORT` | 8081 | Published port |

Separation-of-duties enforcement (`PLM_ENFORCE_SEPARATION_OF_DUTIES`) defaults to on. Turning it off is a
validated-state change.

## CLI (`docker compose exec api python -m app.cli …`)

| Command | Purpose |
|---|---|
| `create-user USER "Full Name" --roles ROLE[,ROLE]` | Create an account (password prompted) |
| `verify-audit` | Verify the audit hash chain. Exit code 2 if broken. |
| `verify-files` | Re-hash every stored file; report MISSING / SIZE_MISMATCH / HASH_MISMATCH / ORPHAN |
| `verify-inventory` | Rebuild balances from the ledger and compare them with the stored balances |
| `version` | Application version and database schema revision |
| `seed-demo` | Demo data (development only) |

Suggested routine: run all three `verify-*` commands weekly, and before and after every backup, restore and
upgrade. Keep the output as a record. `ORPHAN` files come from uploads whose transaction was rolled back; they
are harmless.

## What a broken audit chain means

Verification reports the first event whose hash does not match. Treat it as a data-integrity incident: take a
backup of the current state, compare with the last good backup, and investigate who had privileged database
access. The chain is **tamper-evident, not tamper-proof**: someone with database superuser rights could rewrite
the chain from the altered point onward. Mitigate this by restricting host and database superuser access, and by
recording the chain head (printed by `verify-audit`) in off-system records, for example with each backup.

## Upgrades

1. Read the release notes.
2. Back up (`scripts/backup.sh`).
3. `git pull` (or unpack the release), then `docker compose up -d --build`.
4. The one-shot `migrate` service applies migrations. The API refuses to start if the schema does not match its
   build.
5. Run the `verify-*` commands, check **About this system**, and record the upgrade.

Roll back by restoring the pre-upgrade backup with the previous release's images. Do not run a new database
schema against an old build.

## Logs

`docker compose logs api` shows structured JSON with a request ID per request, which also appears on audit
events. Operational logs are not the audit trail.
