#!/bin/sh
# Runs once, when the database volume is first initialised.
# Creates the least-privilege application login role. Table privileges are granted by the migrations.
set -eu
psql -v ON_ERROR_STOP=1 -v app_pw="$APP_DB_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE qplm_app LOGIN PASSWORD :'app_pw';
REVOKE ALL ON DATABASE qplm FROM PUBLIC;
GRANT CONNECT ON DATABASE qplm TO qplm_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
EOSQL
