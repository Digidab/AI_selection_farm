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
