-- Run automatically by Postgres on first container start via
-- /docker-entrypoint-initdb.d. Enables the pgvector extension so callers
-- can use vector columns without a manual step.
CREATE EXTENSION IF NOT EXISTS vector;
