#!/bin/sh
set -eu

# Official PostgreSQL entrypoint invokes this only when initializing an empty data volume.
INSIGHTRAG_RUNTIME_PASSWORD="$(cat /run/secrets/runtime_db_password)"
export INSIGHTRAG_RUNTIME_PASSWORD
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv runtime_password INSIGHTRAG_RUNTIME_PASSWORD
CREATE ROLE insightrag_runtime LOGIN PASSWORD :'runtime_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE insightrag TO insightrag_runtime;
GRANT USAGE ON SCHEMA public TO insightrag_runtime;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
unset INSIGHTRAG_RUNTIME_PASSWORD
