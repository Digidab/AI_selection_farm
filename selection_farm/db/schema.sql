-- Current full schema snapshot (kept in sync with migrations/).
-- Regenerate this file whenever a new migration is added under db/migrations/.
-- Schema bootstrap only. Tables live in their own numbered migrations.
CREATE SCHEMA IF NOT EXISTS farm;
-- Enable pgvector extension.
CREATE EXTENSION IF NOT EXISTS vector;
-- farm.model_registry — operational record of every model (database_guide.md §4.1).
-- parent_model_id has no FK constraint yet: PE (pedigree) is deferred
-- (configs/id_mapping/ID_DOMAINS.md) and there is no second model to reference.
-- Add the FK constraint only when PE is activated, not before.
CREATE TABLE farm.model_registry (
    id BIGSERIAL PRIMARY KEY,
    model_id TEXT NOT NULL UNIQUE,
    model_name TEXT,
    model_type TEXT NOT NULL,
    base_model TEXT,
    resource_class TEXT NOT NULL,
    generation INT,
    parent_model_id TEXT,
    status TEXT NOT NULL,
    allowed_for_pipeline BOOLEAN NOT NULL DEFAULT false,
    allowed_for_breeding BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- Runtime core tables for Selector/Bereiter/Trainer workflows
-- (database_guide.md §4.2-§4.6). Embeddings and indexes are separate migrations.
CREATE TABLE farm.runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    model_id TEXT REFERENCES farm.model_registry (model_id),
    dataset_id TEXT,
    config_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    total_items INT NOT NULL DEFAULT 0,
    processed_items INT NOT NULL DEFAULT 0,
    accepted_items INT NOT NULL DEFAULT 0,
    rejected_items INT NOT NULL DEFAULT 0,
    failed_items INT NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE farm.tasks (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES farm.runs (run_id),
    task_type TEXT NOT NULL,
    prompt TEXT,
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_schema JSONB,
    status TEXT NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE farm.generations (
    id BIGSERIAL PRIMARY KEY,
    generation_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES farm.tasks (task_id),
    run_id TEXT NOT NULL REFERENCES farm.runs (run_id),
    model_id TEXT NOT NULL REFERENCES farm.model_registry (model_id),
    temperature NUMERIC,
    raw_output TEXT NOT NULL,
    parsed_output JSONB,
    latency_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE farm.validation_results (
    id BIGSERIAL PRIMARY KEY,
    validation_id TEXT NOT NULL UNIQUE,
    generation_id TEXT NOT NULL REFERENCES farm.generations (generation_id),
    validator_version TEXT NOT NULL,
    is_valid BOOLEAN NOT NULL,
    score NUMERIC,
    failure_code TEXT,
    failure_reason TEXT,
    validation_details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE farm.samples (
    id BIGSERIAL PRIMARY KEY,
    sample_id TEXT NOT NULL UNIQUE,
    validation_result_id TEXT NOT NULL REFERENCES farm.validation_results (validation_id),
    task_id TEXT NOT NULL REFERENCES farm.tasks (task_id),
    generation_id TEXT NOT NULL REFERENCES farm.generations (generation_id),
    run_id TEXT NOT NULL REFERENCES farm.runs (run_id),
    model_id TEXT NOT NULL REFERENCES farm.model_registry (model_id),
    dataset_id TEXT,
    status TEXT NOT NULL,
    prompt TEXT,
    completion TEXT,
    failure_code TEXT,
    failure_reason TEXT,
    score NUMERIC,
    selector_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- Embedding vectors for pgvector deduplication and similarity search
-- (database_guide.md §4.7). Indexes, including HNSW, belong to 006_indexes.sql.
CREATE TABLE farm.embeddings (
    id BIGSERIAL PRIMARY KEY,
    embedding_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    embedding_model_id TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
