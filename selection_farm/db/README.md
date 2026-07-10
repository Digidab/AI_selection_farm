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

## Agent Notes

- Keep `schema.sql` synced with the exact concatenation of migrations after adding a new migration.
- Apply only incremental migration files to the existing live database.
- Do not apply the full `schema.sql` to the existing live container; it is a fresh-environment
  snapshot and includes migrations that may already be applied.
- `005_embeddings.sql` owns vector storage; `006_indexes.sql` owns the v001 secondary indexes,
  including HNSW.
- DB integration tests, Selector runtime logic, and Model Lab remain future work; migration `006`
  implements indexes only.
