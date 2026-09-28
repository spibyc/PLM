#!/usr/bin/env bash
# PLM restore. DESTROYS the current database and file store and replaces them with the backup.
# Usage: scripts/restore.sh <backup-dir>
# After restoring, verifies the audit chain, stored file hashes and inventory ledger/balance consistency.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="${1:?Usage: scripts/restore.sh <backup-dir>}"
DC="docker compose"

echo "[1/7] Checking backup integrity"
( cd "$SRC" && sha256sum -c SHA256SUMS )
echo "Backup version: $(cat "$SRC/version.json")"
echo "Running build:  $($DC run --rm --no-deps -T api python -c 'from app.version import EXPECTED_SCHEMA_REVISION as e; print(e)' 2>/dev/null || echo unknown) (expected schema)"
echo
read -r -p "This REPLACES all current PLM data. Type RESTORE to continue: " ans
[ "$ans" = "RESTORE" ] || { echo "Aborted."; exit 1; }

echo "[2/7] Stopping application"
$DC stop gateway api
$DC up -d db
until $DC exec -T db pg_isready -U qplm_owner -d postgres >/dev/null 2>&1; do sleep 1; done

echo "[3/7] Recreating database"
$DC exec -T db psql -v ON_ERROR_STOP=1 -U qplm_owner -d postgres \
  -c "DROP DATABASE IF EXISTS qplm WITH (FORCE)" -c "CREATE DATABASE qplm OWNER qplm_owner"

echo "[4/7] Restoring database"
$DC exec -T db pg_restore -U qplm_owner -d qplm --exit-on-error --no-password < "$SRC/db.dump"
$DC exec -T db psql -v ON_ERROR_STOP=1 -U qplm_owner -d qplm \
  -c "REVOKE ALL ON DATABASE qplm FROM PUBLIC" -c "GRANT CONNECT ON DATABASE qplm TO qplm_app"

echo "[5/7] Restoring file store"
$DC run --rm --no-deps -T --entrypoint sh api -c \
  'chmod -R u+w /data/filestore && find /data/filestore -mindepth 1 -delete && tar -C /data -xf -' \
  < "$SRC/filestore.tar"

echo "[6/7] Starting application"
$DC up -d

echo "[7/7] Post-restore verification"
FAIL=0
$DC exec -T api python -m app.cli verify-audit      || { echo "AUDIT CHAIN VERIFICATION FAILED" >&2; FAIL=1; }
$DC exec -T api python -m app.cli verify-files      || { echo "FILE INTEGRITY VERIFICATION FAILED" >&2; FAIL=1; }
$DC exec -T api python -m app.cli verify-inventory  || { echo "INVENTORY CONSISTENCY CHECK FAILED" >&2; FAIL=1; }
if [ "$FAIL" -ne 0 ]; then
  echo "Restore completed WITH VERIFICATION FAILURES. Do not use the system until investigated." >&2
  exit 2
fi
echo "Restore complete and verified. Record this restore (date, backup ID, verifier) per your procedures."
