-- Secondary indexes for Selection Farm DB v001 (database_guide.md §7).
-- Primary-key and UNIQUE constraint indexes are owned by migrations 003-005.
BEGIN;

CREATE INDEX idx_model_registry_status
ON farm.model_registry (status);

CREATE INDEX idx_runs_run_type
ON farm.runs (run_type);

CREATE INDEX idx_runs_status
ON farm.runs (status);

CREATE INDEX idx_runs_started_at
ON farm.runs (started_at);

CREATE INDEX idx_tasks_status
ON farm.tasks (status);

CREATE INDEX idx_tasks_run_id
ON farm.tasks (run_id);

CREATE INDEX idx_generations_task_id
ON farm.generations (task_id);

CREATE INDEX idx_generations_run_id
ON farm.generations (run_id);

CREATE INDEX idx_generations_model_id
ON farm.generations (model_id);

CREATE INDEX idx_validation_results_generation_id
ON farm.validation_results (generation_id);

CREATE INDEX idx_validation_results_is_valid
ON farm.validation_results (is_valid);

CREATE INDEX idx_validation_results_failure_code
ON farm.validation_results (failure_code);

CREATE INDEX idx_samples_status
ON farm.samples (status);

CREATE INDEX idx_samples_model_id
ON farm.samples (model_id);

CREATE INDEX idx_samples_dataset_id
ON farm.samples (dataset_id);

CREATE INDEX idx_samples_run_id
ON farm.samples (run_id);

CREATE INDEX idx_embeddings_embedding_hnsw
ON farm.embeddings
USING hnsw (embedding vector_cosine_ops);

COMMIT;
