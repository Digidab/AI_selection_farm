# db

## Mission

`db/` owns SQL migrations, the full schema snapshot, and local PostgreSQL/pgvector database
definitions for Selection Farm. The actual PostgreSQL data directory is not committed to Git; see
`postgres_volume/` (bind mount, git-ignored).

Full schema design, versioning strategy, and the database-vs-files ownership rules are documented in
`readmy_info/selection_farm_database_guide.md`.

## Migration Map

- `migrations/001_init.sql` — schema bootstrap for `farm`.
- `migrations/002_add_pgvector.sql` — captures the pgvector extension for fresh environments.
- `migrations/003_model_registry.sql` — operational model registry table.
- `migrations/004_runtime_core.sql` — runtime workflow tables: `runs`, `tasks`, `generations`,
  `validation_results`, `samples`.
- Future `005_embeddings.sql` — embeddings table.
- Future `006_indexes.sql` — performance and pgvector indexes.

## Current Applied State

Task #04 runtime-core migration verdict: `passed`. On 2026-07-09, `004_runtime_core.sql` was applied
to the live `selection_farm_postgres` container, the temporary chain
`_tz04_model -> _tz04_run -> _tz04_task -> _tz04_generation -> _tz04_validation -> _tz04_sample`
was inserted and joined successfully, and all `_tz04_%` rows were cleaned up.

The live `farm` schema now contains `model_registry`, `runs`, `tasks`, `generations`,
`validation_results`, and `samples`.

## Agent Notes

- Keep `schema.sql` synced with the exact concatenation of migrations after adding a new migration.
- Apply only incremental migration files to the existing live database.
- Do not apply the full `schema.sql` to the existing live container; it is a fresh-environment
  snapshot and includes migrations that may already be applied.
