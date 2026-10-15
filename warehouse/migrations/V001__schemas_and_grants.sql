-- Warehouse layers. "audit" is created by the migration runner itself.
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS marts;

-- The BI role reads modelled data only: no access to raw (PII) or staging.
GRANT USAGE ON SCHEMA core, marts, audit TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT ON TABLES TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO bi_reader;
