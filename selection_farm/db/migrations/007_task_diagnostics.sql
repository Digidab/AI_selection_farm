-- Durable task source identity and failure diagnostics for resumable runtimes.
BEGIN;

ALTER TABLE farm.tasks
    ADD COLUMN source_id TEXT,
    ADD COLUMN error_type TEXT,
    ADD COLUMN error_message TEXT,
    ADD COLUMN error_traceback TEXT,
    ADD CONSTRAINT tasks_source_id_nonempty
        CHECK (source_id IS NULL OR btrim(source_id) <> ''),
    ADD CONSTRAINT tasks_error_evidence_complete
        CHECK (
            (error_type IS NULL AND error_message IS NULL AND error_traceback IS NULL)
            OR
            (error_type IS NOT NULL AND error_message IS NOT NULL AND error_traceback IS NOT NULL)
        );

UPDATE farm.tasks
SET source_id = metadata ->> 'source_id'
WHERE metadata ? 'source_id'
  AND btrim(metadata ->> 'source_id') <> '';

UPDATE farm.tasks
SET metadata = metadata - 'source_id'
WHERE metadata ? 'source_id';

CREATE UNIQUE INDEX idx_tasks_run_source_id
ON farm.tasks (run_id, source_id)
WHERE source_id IS NOT NULL;

COMMIT;
