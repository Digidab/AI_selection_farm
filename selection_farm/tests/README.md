# Tests

Automated tests protect Selection Farm from silent degradation. Implemented coverage includes the
PostgreSQL/pgvector v001 integration baseline, Selector architecture isolation, neutral Selector
Core, isolated LLM/ML inputs, deterministic LLM component/Ollama transport contracts, and strict
LLM structured-output/schema/semantic-dedup evaluation plus deterministic ML adapter inference. The
legacy top-level unit and regression modules remain placeholders; Task 13 replaces the Ollama
placeholder with a bounded live structured-generation check.

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

Selector foundation and architecture suites:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/unit/selector/core \
  selection_farm/tests/unit/selector/llm \
  selection_farm/tests/unit/selector/ml \
  selection_farm/tests/integration/test_selector_architecture.py
```

Selector Core live repository suite:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/integration/test_selector_core_repository.py
```

Selector LLM evaluator pgvector integration:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/integration/test_selector_llm_mvp.py
```

Selector ML exact-dedup integration:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/integration/test_selector_ml_mvp.py
```

Selector DB-first export and branch serializer suites:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/unit/selector/core/test_export.py \
  selection_farm/tests/unit/selector/test_export_serializers.py
```

Task 12 assembled pipeline, entrypoint-script, and architecture verification:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/unit/selector \
  selection_farm/tests/integration/test_selector_architecture.py
bash -n selection_farm/scripts/run_selector.sh \
  selection_farm/scripts/run_selector_llm.sh \
  selection_farm/scripts/run_selector_ml.sh
```

Task 13 assembled live branch integration:

```bash
PYTHONDONTWRITEBYTECODE=1 ./venv_ai_selection_farm/bin/pytest -q \
  selection_farm/tests/integration/test_selector_branch_e2e.py
```

## Isolation

The shared `db_connection` fixture opens a function-scoped psycopg connection with
`autocommit=False`. Every test ends with `rollback()` and `close()` in a `finally` block. Runtime
tests use unique task-owned `_tz07_`/`_tz08_` identifiers and do not call project ID-generator
wrappers. Connection failures are test failures rather than skips, and error messages do not expose
resolved settings.

## Implemented DB coverage

- `db/schema.sql` body matches migrations `001-006` in exact order.
- The configured PostgreSQL database is reachable.
- pgvector is installed with the required `hnsw` and `vector_cosine_ops` capabilities.
- The exact v001 catalog contains seven expected tables and 31 expected indexes.
- `idx_embeddings_embedding_hnsw` uses `vector_cosine_ops`.
- A six-table runtime-core FK chain can be inserted, joined, and rolled back.
- Two `vector(768)` embeddings can be inserted and queried with cosine distance; the exact query
  returns the expected nearest candidate.

## Implemented Selector foundation coverage

- `core`, `llm`, and `ml` packages import and obey `llm -> core <- ml`.
- Seeded forbidden imports are detected by the AST architecture guard.
- Common YAML parsing is strict, rejects unknown/missing keys, and resolves paths independently of CWD.
- Neutral lifecycle records, decisions, errors, branch protocol fakes, and correlation logging are tested.
- LLM config enforces the exact v001 component profile and rejects missing, unknown, duplicate,
  cross-branch, and incompatible selections.
- LLM task records enforce one prompt/message form and a valid expected JSON Schema; deterministic
  branch-owned JSONL fixtures parse without runtime or network access.
- ML config enforces typed ordered features, explicit `sklearn_generic`, classification/regression
  rules, optional confidence, finite numbers, and safe artifact paths.
- ML task records reject missing/extra/type-invalid features and canonicalize exact input identity
  independently of JSON key order; those schema checks do not load artifacts or run inference.
- ML pipeline tests use tmp-path joblib/scikit-learn classification and regression fixtures,
  preserve config feature order, call probabilities only when required, normalize typed evidence,
  reject artifact/API failures, and prove registry substitution without family dispatch changes.
- ML validation tests cover class/range/probability/confidence boundaries, auditable failures,
  validation-before-lookup ordering, canonical key-order independence, and strict numeric types.
- The live ML lookup case compares only accepted same-dataset ML task payloads, excludes rejected,
  cross-dataset, and other-branch rows, and creates no ML-owned vector evidence.
- Core repository tests cover injectable IDs, legal/illegal transitions, atomic counters,
  evidence-driven resume, and idempotent generation/validation/sample/vector persistence.
- LLM component tests cover runtime-checkable protocols, allowlisted registration, capability
  incompatibility, test-only adapter injection, stable text preparation, and single-turn delegation.
- Mocked Ollama tests assert exact non-streaming generate/embed payloads, typed responses, timeouts,
  two-attempt transient retry, 404 fail-closed behavior, and exact finite 768-value vectors.
- LLM evaluator tests cover strict object JSON, size/depth limits, deterministic canonicalization,
  Draft 2020-12 schema failures before embedding, complete component-scoped evidence, inclusive
  cosine threshold behavior, and fail-closed embedding errors.
- The live pgvector evaluator case restricts nearest-neighbor lookup to accepted samples in the
  same LLM dataset and embedding space, excluding ML and cross-dataset rows.
- Export tests cover distinct LLM/ML golden shapes, mandatory branch evidence, deterministic sample
  ordering, byte-stable repeated publication, and restoration of all previous files after an
  injected replacement or serialization failure.
- Task 12 pipeline tests execute independent fake LLM/ML accept and reject paths, resume both branch
  identities from persisted generations without repeated execution, reject the wrong registry model
  type before creating a run, and expose/count partial failure. Script tests cover shell syntax,
  explicit allowlisted dispatch, `BASH_SOURCE[0]`, workspace venv resolution, and arbitrary CWD.
- Task 13 assembled live integration uses two temporary DB model rows, a protocol-compatible mocked
  LLM runtime with exact 768D evidence, and a pytest-owned joblib/sklearn artifact. Both branches
  complete with exact `total=processed=accepted=1` counters; LLM owns one embedding and ML owns
  none; four DB-first exports are branch-distinct and byte-stable; wrong model type creates no run.
- Verified after Task 13 on 2026-07-12: Selector unit + architecture matrix passed `170/170`; full
  integration passed `15/15` (two upstream NumPy/joblib deprecation warnings); targeted assembled
  live E2E passed `1/1`; the final combined Selector unit + full integration run passed `181/181`.
  Final DB audit returned zero `_tz08_` rows in all seven tables, no `_tz08_` files remained, and
  production ID counters were unchanged.
- Live Ollama Task 13 verdict: `qwen3:0.6b` bounded structured generation passed with
  `{"status":"nominal"}`. Full provider E2E is precisely `inconclusive` because the mandatory
  `nomic-embed-text` model is unavailable; no pull, install, or fallback was attempted.
- Verified after Task 12 on 2026-07-12: deterministic Selector unit + architecture suite passed
  `170/170`; Ruff and three-script shell syntax checks passed; both explicit branch help paths ran
  successfully from `/tmp`.
- Verified after Task 11 on 2026-07-12: deterministic Selector unit + architecture suite passed
  `156/156`; targeted export/serializer suite passed `9/9`; shell syntax and host DB-first export
  passed. Repeated live publication produced the same four empty DB-owned files for the empty
  baseline with no temporary/backup residue.
- Task 10 scoped live ML exact-dedup plus Core repository suite passed `3/3`, created no ML-owned
  vector evidence, and left zero `_tz08_` rows in all seven tables.
- The earlier scoped live LLM evaluator plus Core repository suite passed `3/3` with full cleanup.
- Task 7 live Ollama check: health `200`; `qwen3:0.6b` structured generation passed; embedding was
  precisely inconclusive because `nomic-embed-text` is not installed. No pull or fallback occurred.

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

## Remaining placeholders

- `unit/test_selector_validators.py`
- `unit/test_schemas.py`
- `unit/test_dataset_writer.py`
- `regression/test_generation_regression.py`

Future test work still includes live Ollama embedding connectivity when the approved model is
available and generation regression coverage. Git publication remains Task 14.
