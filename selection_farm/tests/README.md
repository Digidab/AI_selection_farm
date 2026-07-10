# Tests

Automated tests protect Selection Farm from silent degradation. The current implemented coverage
is the PostgreSQL/pgvector v001 integration baseline; Ollama, unit, and regression test modules are
still placeholders.

## PostgreSQL integration prerequisites

- Run commands from the repository root.
- The local `selection_farm_postgres` container must be running with the v001 schema applied.
- Connection defaults come from the ignored `selection_farm/docker/.env` file. Process environment
  values override local defaults.
- Never commit or print `.env` credentials.
- Use `./venv_ai_selection_farm/bin/pytest`; the project virtual environment contains the required
  `pytest`, `psycopg`, `pgvector`, and `python-dotenv` packages.

## Commands

Targeted DB integration suite:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/integration/test_postgres_connection.py \
  selection_farm/tests/integration/test_runtime_core_persistence.py \
  selection_farm/tests/integration/test_pgvector_dedup.py
```

Full integration directory:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/integration
```

## Isolation

The shared `db_connection` fixture opens a function-scoped psycopg connection with
`autocommit=False`. Every test ends with `rollback()` and `close()` in a `finally` block. Runtime
tests use unique `_tz07_` identifiers and do not call project ID-generator wrappers. Connection
failures are test failures rather than skips, and error messages do not expose resolved settings.

## Implemented DB coverage

- `db/schema.sql` body matches migrations `001-006` in exact order.
- The configured PostgreSQL database is reachable.
- pgvector is installed with the required `hnsw` and `vector_cosine_ops` capabilities.
- The exact v001 catalog contains seven expected tables and 31 expected indexes.
- `idx_embeddings_embedding_hnsw` uses `vector_cosine_ops`.
- A six-table runtime-core FK chain can be inserted, joined, and rolled back.
- Two `vector(768)` embeddings can be inserted and queried with cosine distance; the exact query
  returns the expected nearest candidate.

## Verified runtime checkpoint

Verified on 2026-07-10:

- Verdict: `passed`.
- Targeted DB suite: `5 passed`, exit code `0`.
- Full integration directory: `6 passed`, exit code `0`.
- Live database: `selection_farm`.
- pgvector extension: `0.5.1`; `hnsw` and `vector_cosine_ops` available.
- Final catalog: seven exact v001 tables and 31 exact v001 indexes.
- Independent post-run cleanup: zero `_tz07_` rows in `model_registry`, `runs`, `tasks`,
  `generations`, `validation_results`, `samples`, and `embeddings`.

The full integration count includes `test_ollama_connection.py::test_placeholder`; it does not
represent implemented Ollama coverage.

## Remaining placeholders

- `integration/test_ollama_connection.py`
- `unit/test_selector_validators.py`
- `unit/test_schemas.py`
- `unit/test_dataset_writer.py`
- `regression/test_generation_regression.py`

Future test work still includes JSON/schema validation, empty input, NaN/Inf and range rejection,
resume-after-interruption behavior, dataset writing, Ollama connectivity, and generation
regression coverage.
