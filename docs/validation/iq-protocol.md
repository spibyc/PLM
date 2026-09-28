# IQ protocol — PLM (template)

Protocol ID: ________  Version: ____  Approved by: ____________ Date: ______

| # | Check | Method | Expected | Actual | Pass/Fail | Initials/Date |
|---|---|---|---|---|---|---|
| IQ-1 | Host meets spec (CPU, RAM, disk, OS) | Inspect | Per deployment.md | | | |
| IQ-2 | Docker/Compose versions recorded | `docker version`, `docker compose version` | Recorded | | | |
| IQ-3 | Release identity | Record git tag/commit or archive SHA-256 | Matches approved release | | | |
| IQ-4 | `.env` secrets unique, file mode 600, not in version control | Inspect | Yes | | | |
| IQ-5 | Stack starts | `docker compose up -d --build`; `docker compose ps` | db, api, gateway healthy; migrate exited 0 | | | |
| IQ-6 | Version and schema | About page / `app.cli version` | Version as released; schema = expected | | | |
| IQ-7 | HTTPS in place, cookie secure | Browser inspect; `.env` | TLS valid; `COOKIE_SECURE=true` | | | |
| IQ-8 | Only 443/80 reachable from the network | Port scan | Yes | | | |
| IQ-9 | NTP synchronised | `timedatectl` | Synchronised | | | |
| IQ-10 | Default roles present | Users & roles page | 6 roles as admin-guide.md | | | |
| IQ-11 | Initial admin created via CLI; no demo data | Inspect users; `PLM_ENVIRONMENT=production` | Yes | | | |
| IQ-12 | Backup runs; restore tested on separate instance | backup-restore.md | All verifications pass | | | |
| IQ-13 | Automated test suite result for this release attached | trace-matrix.md with results | All PASS | | | |
