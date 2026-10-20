#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password GCS_DB_PASSWORD
CREATE USER gcs WITH PASSWORD :'app_password';
CREATE DATABASE gcs OWNER gcs;
SQL
