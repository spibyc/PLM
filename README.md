# PLM

**PLM** is a self-hosted product lifecycle, engineering data, inventory, supplier and controlled-document database. It is intended to give small engineering teams and individual makers one place to manage the information that normally ends up spread across spreadsheets, shared drives, purchasing portals and paper records.

It can be used as a lightweight database for personal engineering projects or configured with controlled workflows to support a regulated quality-management system.

> **Regulatory note:** PLM includes controls intended to support document, record, supplier, traceability and approval processes used in ISO 13485 environments. Installing the software does **not** make an organisation ISO 13485 compliant or certified. A regulated deployment must define its own procedures, responsibilities, retention rules and intended use, and validate the software for that intended use.

## What PLM manages

| Area | Capability |
|---|---|
| Parts & components | Internal part numbers, revisions, lifecycle state, manufacturer parts, datasheets and engineering files |
| Manufacturer & purchasing sources | Manufacturer part numbers plus one or more distributor/supplier order codes and URLs |
| Suppliers | Supplier register, qualification/approval state, suspension/reinstatement and audit history |
| Purchasing | Purchase orders and controlled purchasing traceability |
| Inventory | Locations, QR labels, lots, receipts, inspection, issue/return, transfer, adjustment, scrap and quarantine |
| BOMs | Controlled BOMs and released BOM revisions |
| Production | Builds, serial numbers, material genealogy and where-used traceability |
| Documents | Controlled document register, revisions, review/release, supersession, obsolescence, retention and file hashes |
| Quality & administration | Roles/permissions, electronic signatures, audit trail and administrative override logging |
| Change control | ECR/ECO is on the roadmap and remains visibly marked as planned |

The controlled traceability chain is designed around **Supplier → Purchase Order → Receipt → Lot → Released BOM → Build → Serial**, while the document register provides a parallel controlled history for procedures, specifications, drawings, reports and other records.

## Branding your installation

Branding is deliberately kept outside the application source. You do **not** need to edit React code to make a work, home or customer-specific installation.

The folder is:

```text
branding/
├── branding.js
└── logo.png
```

### Change the logo

Replace `branding/logo.png` with your own PNG while keeping the filename `logo.png`.

For example, for a company installation:

```bash
cp ~/Pictures/company-logo.png branding/logo.png
```

The branding directory is mounted into the web container at runtime, so the company logo is not baked into the source code or Docker image. Refresh the browser after replacing it. Browser caching may require a hard refresh.

### Change the displayed organisation name

Edit `branding/branding.js`:

```javascript
window.PLM_BRANDING = {
  productName: "PLM",
  organizationName: "Example Engineering Ltd",
  tagline: "Product Lifecycle Management",
  logoPath: "/branding/logo.png",
  logoAlt: "Example Engineering logo"
};
```

A personal installation could instead use:

```javascript
window.PLM_BRANDING = {
  productName: "PLM",
  organizationName: "Home Lab",
  tagline: "Engineering Database",
  logoPath: "/branding/logo.png",
  logoAlt: "Home Lab logo"
};
```

To restore a company-specific deployment later, simply copy that company's `logo.png` into `branding/` and set `organizationName`/`tagline` in `branding.js`. Keep proprietary company artwork in a private deployment repository or outside Git; the public PLM repository can retain the generic logo supplied here.

## Quick deployment

### Requirements

- Docker Engine
- Docker Compose v2, or the older `docker-compose` command
- A machine with persistent storage for PostgreSQL and the file store

Clone the repository and create your local environment file:

```bash
git clone <your-repository-url> plm
cd plm
cp .env.example .env
```

Generate two different database passwords:

```bash
openssl rand -hex 24
openssl rand -hex 24
```

Put those values into `.env` as `POSTGRES_PASSWORD` and `APP_DB_PASSWORD`. Do not commit `.env`.

For a normal local installation, the defaults expose PLM on port `8081`:

```bash
docker compose up -d --build
```

On systems using legacy Compose:

```bash
docker-compose up -d --build
```

Open:

```text
http://localhost:8081
```

Create the first administrator. The password is requested interactively and is not placed on the command line:

```bash
docker compose exec api python -m app.cli create-user admin "Administrator" --roles ADMIN
```

Legacy Compose equivalent:

```bash
docker-compose exec api python -m app.cli create-user admin "Administrator" --roles ADMIN
```

Then sign in and create the remaining users and roles from **Quality & admin → Users & roles**.

## Configuration

`.env.example` documents the normal deployment settings. Important values include:

```text
HTTP_PORT=8081
PUBLIC_BASE_URL=http://localhost:8081
COOKIE_SECURE=false
PLM_ENVIRONMENT=production
SESSION_IDLE_MINUTES=30
MAX_UPLOAD_MB=50
PLM_VERSION=0.3.1
```

Set `PUBLIC_BASE_URL` before printing QR labels because generated links use this address. For a network deployment, use the hostname or HTTPS URL users will actually access.

For production use, terminate TLS/HTTPS correctly and set `COOKIE_SECURE=true`; see `docs/deployment.md`.

## Public viewer access

Anyone who can reach PLM can browse parts (including revisions and attached files), lots,
locations and their stock contents, and stock transactions without signing in. QR labels
open these read-only pages directly. The account menu shows **Public viewer · read only**;
choose **Sign in to edit** for staff access. Public viewers cannot change records, upload,
inspect, approve, or access the dashboard, audit trail, user administration, purchasing,
production, or controlled document register. Signing out returns to public viewing.

After deploying this change, rebuild both application services:

```bash
sudo docker compose up -d --build
```

## Data persistence

Application data is **not stored in the Git repository**. Docker volumes hold the PostgreSQL database and controlled filestore. The `branding/` directory contains only deployment branding.

Do not run `docker compose down -v` unless you intentionally want to delete the installation's Docker volumes. Normal upgrades should stop containers **without** `-v`.

Backup and restore procedures are documented in `docs/backup-restore.md` and scripts are provided under `scripts/`.

## Controlled documents

**Engineering → Documents** provides the document register. A document has a stable document identity and separate revisions. A typical controlled workflow is:

```text
Create document → Draft revision → Upload file → Review → Signed release
                                      ↓
                              later create new revision
                                      ↓
                         release new revision → old release retained as Superseded
```

Released files are retained with SHA-256 integrity hashes. Obsolescence is recorded rather than deleting historical revisions. Metadata supports ownership, document type, effective date, periodic review and retention information.

For an ISO 13485 deployment, configure and validate these workflows against the organisation's actual document-control and record-control procedures rather than treating the software defaults as regulatory requirements.

## Suppliers and purchasing sources

A **Supplier** is an organisation you purchase goods or services from. Examples include distributors, PCB assemblers, machine shops, calibration laboratories and contract manufacturers.

A manufacturer part can then have one or more purchasing sources, for example:

```text
Internal Part
└── Manufacturer Part
    ├── Distributor A → order code → product URL
    └── Distributor B → order code → product URL
```

This keeps the engineering identity of a component separate from where it happens to be purchased.

## Architecture

```text
browser ──► gateway (nginx) ──/api──► API (FastAPI) ──► PostgreSQL 16
                 │                         │
                 │                         └── content-addressed filestore
                 └── runtime branding/

migrate (one-shot) ──► Alembic migrations + role bootstrap
```

The backend network is internal and only the gateway is published. Database migrations run using the schema-owner account while normal application access uses a restricted database role.

Some internal database role/function names retain the historical `qplm_*` prefix so existing installations can upgrade without destructive database renaming. These are implementation details and are not product or organisation branding.

## Security and audit model

PLM includes Argon2id password hashing, sessions, CSRF protection, login lockout/rate limiting, role-based permissions, electronic re-authentication for signatures, an append-only hash-chained audit trail, controlled-file hashes and database-level guards for important released/append-only records.

The ADMIN role has the project's deliberately configured superuser override capability. Exceptional corrections remain audit logged; foreign-key relationships can still prevent destructive deletion of referenced records.

## Updating an existing installation

Back up first. Then stop the old checkout without deleting volumes, replace/update the source, preserve your `.env`, and start the new checkout using the **same Compose project name** so it reconnects to the existing volumes.

If an older installation was previously run as project `qplm`, use that project name during the migration:

```bash
docker compose -p qplm down
# from the new PLM checkout, with the old .env copied in:
docker compose -p qplm up -d --build
```

After you intentionally migrate to a fresh installation you may use the new default Compose project name `plm`. Do not casually change the project name on an existing deployment: Compose project names affect volume names.

## Repository hygiene before publishing to GitHub

The supplied `.gitignore` excludes `.env`, backups, build output, caches and local Python environments. Before making a repository public, still review it yourself:

```bash
git status
find . -maxdepth 3 -type f | sort
rg -n -i 'password|secret|token|api[_-]?key|private[_-]?key|company-name' . \
  --glob '!frontend/package-lock.json'
```

Do not commit a private company logo, real `.env`, database dumps, filestore contents, exported audit trails, supplier/customer records or controlled company documents.

Choose and add the software licence you want before treating the public repository as an open-source project. No licence choice is assumed on your behalf by this release.

## Development

Backend tests require a disposable PostgreSQL 16 instance:

```bash
cd backend
pip install -r requirements-dev.txt
PLM_TEST_SUPERUSER_URL=postgresql+psycopg://postgres:postgres@localhost/postgres pytest
```

Frontend development:

```bash
cd frontend
npm ci
npm run dev
```

Never point the automated backend test suite at a production database.

## Documentation

- `docs/user-guide.md` — day-to-day workflows
- `docs/admin-guide.md` — users, roles, configuration and administration
- `docs/deployment.md` — deployment, HTTPS and hardening
- `docs/backup-restore.md` — backup and restore
- `docs/validation/` — SRS, traceability matrix, IQ and OQ templates
- `docs/design/` — architecture, data model, permissions and risks
- `CHANGELOG.md` — release history

## Version 0.3.1

0.3.1 removes organisation-specific branding and changes the public product name from **QPLM** to **PLM**. Branding now lives in the runtime `branding/` folder, allowing the same codebase to be used for a company installation, a personal engineering database, or another organisation without modifying application source.
