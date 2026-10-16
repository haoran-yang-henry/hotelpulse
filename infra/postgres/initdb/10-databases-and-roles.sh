#!/usr/bin/env bash
# Creates the logical databases and least-privilege roles.
# Runs once, when the Postgres data volume is initialised (docker-entrypoint-initdb.d).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v airflow_pw="$AIRFLOW_DB_PASSWORD" \
  -v metabase_pw="$METABASE_DB_PASSWORD" \
  -v pms_admin_pw="$PMS_ADMIN_PASSWORD" \
  -v pms_reader_pw="$PMS_READER_PASSWORD" \
  -v dwh_etl_pw="$DWH_ETL_PASSWORD" \
  -v bi_reader_pw="$BI_READER_PASSWORD" \
  -v insight_pw="$INSIGHT_DB_PASSWORD" <<'SQL'
-- Application metadata databases
CREATE ROLE airflow LOGIN PASSWORD :'airflow_pw';
CREATE DATABASE airflow OWNER airflow;
CREATE ROLE metabase LOGIN PASSWORD :'metabase_pw';
CREATE DATABASE metabase OWNER metabase;

-- Simulated source system (PMS): writer + read-only extraction account
CREATE ROLE pms_admin LOGIN PASSWORD :'pms_admin_pw';
CREATE ROLE pms_reader LOGIN PASSWORD :'pms_reader_pw';
CREATE DATABASE pms OWNER pms_admin;

-- Warehouse: pipeline owner + read-only BI account
CREATE ROLE dwh_etl LOGIN PASSWORD :'dwh_etl_pw';
CREATE ROLE bi_reader LOGIN PASSWORD :'bi_reader_pw';
CREATE DATABASE dwh OWNER dwh_etl;

-- "Explain this chart" service: may only read and write schema insight (ADR-0017)
CREATE ROLE insight_app LOGIN PASSWORD :'insight_pw';

REVOKE ALL ON DATABASE pms, dwh, airflow, metabase FROM PUBLIC;
GRANT CONNECT ON DATABASE pms TO pms_reader;
GRANT CONNECT ON DATABASE dwh TO bi_reader, insight_app;
SQL

# pms_reader may read the PMS application tables (schema public) but never the
# simulator's timeline (schema sim), so the pipeline cannot "see the future".
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pms <<'SQL'
GRANT USAGE ON SCHEMA public TO pms_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE pms_admin IN SCHEMA public GRANT SELECT ON TABLES TO pms_reader;
SQL
