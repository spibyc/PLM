#!/usr/bin/env bash
# PLM backup: database (pg_dump custom format) + controlled file store + SHA-256 manifest.
# Usage: scripts/backup.sh [output-root]        (default ./backups)
# Order matters: the DB is dumped first, then files. Files are written before their DB rows commit and are
# never modified, so every file referenced by the dump is guaranteed to be in the archive.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="${1:-./backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/plm-$TS"
mkdir -p "$OUT"
DC="docker compose"

echo "[1/5] Recording version"
$DC exec -T api python -m app.cli version > "$OUT/version.json"

echo "[2/5] Verifying audit chain before backup"
if ! $DC exec -T api python -m app.cli verify-audit > "$OUT/audit-chain.json"; then
  echo "WARNING: audit chain verification FAILED. Backup continues; investigate before relying on it." >&2
fi

echo "[3/5] Dumping database"
$DC exec -T db pg_dump -U qplm_owner -d qplm --format=custom --no-password > "$OUT/db.dump"
test -s "$OUT/db.dump"

echo "[4/5] Archiving file store"
$DC exec -T api tar -C /data -cf - filestore > "$OUT/filestore.tar"
test -s "$OUT/filestore.tar"

echo "[5/5] Writing manifest"
( cd "$OUT" && sha256sum version.json audit-chain.json db.dump filestore.tar > SHA256SUMS )
cat > "$OUT/README.txt" <<TXT
PLM backup taken $TS (UTC)
Verify:  (cd $(basename "$OUT") && sha256sum -c SHA256SUMS)
Restore: scripts/restore.sh $OUT
TXT
echo "Backup complete: $OUT"
echo "Copy this directory OFF the host (the backup is not a backup until it is somewhere else)."
