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
- `migrations/005_embeddings.sql` — embeddings storage table for pgvector deduplication and
  similarity search.
- `migrations/006_indexes.sql` — 16 runtime-core B-tree indexes and one pgvector HNSW cosine
  index.
- `migrations/007_task_diagnostics.sql` — durable task `source_id`, item-level error evidence, and
  the unique per-run source identity index.

## Current Applied State

Task #04 runtime-core migration verdict: `passed`. On 2026-07-09, `004_runtime_core.sql` was applied
to the live `selection_farm_postgres` container, the temporary chain
`_tz04_model -> _tz04_run -> _tz04_task -> _tz04_generation -> _tz04_validation -> _tz04_sample`
was inserted and joined successfully, and all `_tz04_%` rows were cleaned up.

The live `farm` schema now contains `model_registry`, `runs`, `tasks`, `generations`,
`validation_results`, `samples`, and `embeddings`.

Task #05 embeddings migration verdict: `passed`. On 2026-07-10, only the incremental
`005_embeddings.sql` migration was applied to the live `selection_farm_postgres` container. Two
temporary `vector(768)` rows were inserted, exact cosine-distance search returned the expected
nearest embedding at distance `0.000000`, and all `_tz05_%` smoke-test rows were cleaned up.

Task #06 indexes migration verdict: `passed`. On 2026-07-10, only the incremental
`006_indexes.sql` migration was applied to the live `selection_farm_postgres` container. The live
`farm` schema now has 31 indexes: 14 constraint-owned indexes from primary-key and unique
constraints plus 17 migration-owned secondary indexes. All 17 catalog definitions matched the
migration contract. With sequential scans disabled for the smoke session, the canonical cosine
query used `idx_embeddings_embedding_hnsw`, returned `_tz06_embedding_a` at distance `0.000000`,
and cleanup left zero `_tz06_%` rows.

Task #07 DB integration-test verdict: `passed`. On 2026-07-10, the targeted PostgreSQL/pgvector
suite passed all five tests and the full integration directory passed all six tests, with the
Ollama test explicitly still a placeholder. The tests verified the exact seven-table/31-index
catalog, schema snapshot parity with migrations `001-006`, the runtime-core FK round trip, and
`vector(768)` cosine behavior. Independent cleanup verification found zero `_tz07_` rows in all
seven v001 tables.

Maintenance migration #007 verdict: `passed`. On 2026-07-13, only the incremental
`007_task_diagnostics.sql` migration was applied to the live container. `farm.tasks` now owns the
dedicated nullable `source_id`, `error_type`, `error_message`, and `error_traceback` columns;
`idx_tasks_run_source_id` enforces unique non-null source identity within a run. Backfill and
metadata cleanup touched zero rows because the live baseline was empty. The current live catalog
contains the same seven tables and 32 indexes, and targeted catalog/repository tests passed `6/6`.

## Agent Notes

- Keep `schema.sql` synced with the exact concatenation of migrations after adding a new migration.
- Apply only incremental migration files to the existing live database.
- Do not apply the full `schema.sql` to the existing live container; it is a fresh-environment
  snapshot and includes migrations that may already be applied.
- `005_embeddings.sql` owns vector storage; `006_indexes.sql` owns the v001 secondary indexes,
  including HNSW; `007_task_diagnostics.sql` owns task source identity and failure diagnostics.
- DB integration tests are implemented under `tests/integration/`; their commands, isolation
  contract, runtime verdict, and remaining placeholders are documented in `tests/README.md`.
- Selector runtime is implemented; Model Lab remains future work. Do not reapply migration `007`
  to a database where its task columns already exist.
