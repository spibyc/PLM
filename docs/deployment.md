# Production deployment

## Checklist

1. A dedicated host or VM (4 GB RAM and 2 vCPU is ample for small teams), with Docker Engine and Compose v2.
2. `.env` created from `.env.example` with unique random passwords (alphanumeric, `openssl rand -hex 24`), file
   mode `600`, never committed.
3. **HTTPS in front of the gateway**, with `COOKIE_SECURE=true` and `PUBLIC_BASE_URL=https://…`. Passwords and
   signatures must not cross the network in clear text.
4. Firewall: expose only 443 (and 80 for redirect). Bind the gateway to localhost when the TLS proxy runs on the
   same host: `HTTP_PORT=127.0.0.1:8081`.
5. NTP time synchronisation on the host. Audit timestamps come from the database clock.
6. Backups scheduled and copied off-host (see `backup-restore.md`), and a restore tested before go-live.
7. Restricted host access. Anyone with Docker or root access on the host can reach the database as superuser.
8. IQ/OQ executed and approved (`docs/validation/`) before use for regulated records.

## TLS reverse proxy examples

Caddy (automatic certificates on a public name, or `tls internal` for an internal CA):

```
plm.example.internal {
    reverse_proxy 127.0.0.1:8081
}
```

nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name plm.example.internal;
    ssl_certificate     /etc/ssl/plm.crt;
    ssl_certificate_key /etc/ssl/plm.key;
    add_header Strict-Transport-Security "max-age=31536000" always;
    client_max_body_size 60m;
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

If you use TrueNAS SCALE or another appliance with its own reverse proxy or ingress, point it at the gateway
port in the same way, and keep the `pgdata` and `filestore` volumes on a dataset with snapshots enabled.
Snapshots complement `scripts/backup.sh`; they do not replace it, because only the scripted backup is
application-consistent and verified.

## Notes and limits (0.1.0)

- The login rate limit is kept in memory per API worker (2 workers). Add rate limiting at the TLS proxy for
  stronger protection.
- The interactive API docs at `/api/docs` load Swagger assets from a CDN. The spec itself is available offline
  at `/api/openapi.json`.
- The migrator uses the Postgres image's initial user, which is a superuser inside the database container. The
  running API uses the least-privilege `qplm_app` role only.
- If `APP_DB_PASSWORD` changes after first start, update the role manually:
  `docker compose exec db psql -U qplm_owner -d qplm -c "ALTER ROLE qplm_app PASSWORD '…'"`.
