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
