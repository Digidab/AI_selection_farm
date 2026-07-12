# Selection Farm — Database Guide

## Purpose of this document

This document defines the PostgreSQL + pgvector schema for **Selection Farm**: its philosophy, the
minimal v001 core, what is deliberately deferred to v002, and — most importantly — which facts live
in the database versus which facts live in files under `studbook/` and `datasets/`.

It follows the same style as `selection_farm_project_structure_guide.md` and should be read together
with it and with `PROJECT_PHILOSOPHY.md`.

Infrastructure status (see `SELECTION_FARM_SOFTWARE_STACK.md` for details):

```text
Postgres + pgvector : running (container selection_farm_postgres, bind mount db/postgres_volume/)
Schema applied       : YES — migrations 001-006, 7 v001 tables and 31 indexes verified live
```

This guide defines the implemented design represented by `db/schema.sql` and
`db/migrations/001`–`006` (see §2). For an existing live database, apply only a new incremental
migration; do not reapply the full snapshot.

---

## 1. Database philosophy

### 1.1. Why a database at all

Files (`datasets/`, `studbook/`) are good at being portable, human-readable, and git-diffable. They
are bad at answering questions that require joins, aggregation, or fast lookups by a key that isn't
the filename — e.g. "which runs used model X", "how many tasks are still pending after a crash",
"which generations are near-duplicates of each other".

The database exists specifically for that second category: **live, high-frequency, queryable
operational state**. It is the mechanism behind the project's own "Safe interruption rule"
(`PROJECT_PHILOSOPHY.md`, §12) — a `status` column that a resumed process can query is what makes
"stop the farm at any time, restart later" actually work in practice, not just in principle.

### 1.2. One fact, one source of truth

The single biggest risk in a schema like this is **the same fact living in two places** — a file and
a table — that a human or a script has to remember to keep in sync. Nothing enforces that sync
automatically, so it drifts, and then nobody knows which one is correct.

Rule for this project:

```text
Every fact has exactly one authoritative owner: either the database, or a file.
The other representation, if it exists, is a GENERATED export — never hand-maintained in parallel.
```

Section 9 of this document ("Database vs. files — who owns what") applies this rule concretely to
every overlap between `farm.*` tables and `studbook/`/`datasets/` files.

### 1.3. Dedicated schema

All project tables live in a dedicated `farm` schema, not `public`:

```sql
CREATE SCHEMA IF NOT EXISTS farm;
CREATE EXTENSION IF NOT EXISTS vector;
```

This keeps the database namespace clean if other tools (Portainer's own metadata, future extensions)
ever share the same Postgres instance.

---

## 2. Versioning strategy

```text
v001 = minimal core: enough to run task → generation → validation → sample, end to end
v002 = extensions added only once v001 is actually being used and the need is concrete
```

This mirrors the project's general "MVP first" rule (`SELECTION_FARM_SOFTWARE_STACK.md`, Final
rule). A schema designed for a scale and complexity the project doesn't have yet is just as much
premature work as installing a fine-tuning stack before the Selector exists.

Migrations stay one file per logical change. The three stub files that already exist in the repo
keep their names and get a specific, dependency-safe purpose; new tables that don't fit get new
numbered files rather than being crammed into `001`:

```text
db/migrations/001_init.sql             → CREATE SCHEMA farm; (schema bootstrap only)
db/migrations/002_add_pgvector.sql     → CREATE EXTENSION IF NOT EXISTS vector;
                                          (already applied manually once on the running container -
                                          must still be captured here so a fresh environment gets it.
                                          Must run before any table with a vector(...) column.)
db/migrations/003_model_registry.sql   → farm.model_registry
db/migrations/004_runtime_core.sql     → farm.runs, farm.tasks, farm.generations,
                                          farm.validation_results, farm.samples
db/migrations/005_embeddings.sql       → farm.embeddings (depends on 002 for the vector type)
db/migrations/006_indexes.sql          → all indexes from §7, including the HNSW index
db/schema.sql                          → full schema snapshot, kept in sync with migrations/
```

The dependency that matters: **002 (extension) must run before 005 (embeddings)** — a table
using `vector(768)` cannot be created until the type exists. `001` and `003`/`004` don't touch
vector columns, so their relative order versus `002` doesn't matter, but keeping `002` early
avoids having to think about it.

---

## 3. v001 core — block scheme

```text
farm.model_registry     # model passports (operational index, not the human-readable one)
farm.runs                # one row per selector/bereiter/trainer execution
farm.tasks                # input tasks, resumable via status
farm.generations          # raw model output per task
farm.validation_results   # pass/fail verdict per generation
farm.samples               # accepted/rejected samples, unified (not split golden/rejected tables)
farm.embeddings             # vectors for pgvector dedup / similarity search
```

Seven tables, not ten. Two tables from the original draft plan are intentionally deferred — see
§8.

---

## 4. Table definitions

### 4.1. `farm.model_registry`

**Purpose:** the operational record of every model the farm knows about. This is what `runs` and
`generations` join against — it must exist and be fast to query from day one.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `model_id` | text, unique | e.g. `qwen3_0_6b_gen_001` |
| `model_name` | text | |
| `model_type` | text | `llm`, `ml`, `hybrid`, `embedding`, `judge`, `reward` |
| `base_model` | text | e.g. `qwen3:0.6b` |
| `resource_class` | text | matches the project's resource buckets: `0.6b_1b`, `1.5b_1.7b`, `3b`, `4b`, `7b_plus`, `classical_ml` (non-LLM models aren't measured in params) |
| `generation` | int, nullable | breeding generation number; null until GE (breeding generations) is activated |
| `parent_model_id` | text, nullable | self-reference for lineage; no FK constraint until PE (pedigree) is activated — see `configs/id_mapping/ID_DOMAINS.md` |
| `status` | text | `raw_candidate`, `trained_candidate`, `tested_candidate`, `breeding_model`, `worker_model`, `rejected_model`, `archived_model` |
| `allowed_for_pipeline` | bool | |
| `allowed_for_breeding` | bool | |
| `created_at`, `updated_at` | timestamptz | |
| `metadata` | jsonb | escape hatch — see "Agent operating rules", rule 2, don't let real fields hide here |

### 4.2. `farm.runs`

**Purpose:** one row per execution of Selector, Bereiter, or Trainer. Gives every task/generation a
way to say "which run produced me", and gives a restarted process something to query for
"what was I in the middle of".

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `run_id` | text, unique | |
| `run_type` | text | `selector`, `bereiter`, `trainer`, `embedding`, `export`, `smoke_test` |
| `status` | text | `pending`, `running`, `paused`, `completed`, `failed`, `cancelled` |
| `model_id` | text, FK → `model_registry.model_id`, nullable | |
| `dataset_id` | text, nullable | **label only, no FK** — see §9.2 |
| `config_id` | text, nullable | references a file under `configs/`, not a table |
| `started_at`, `finished_at` | timestamptz | |
| `total_items`, `processed_items`, `accepted_items`, `rejected_items`, `failed_items` | int | |
| `error_message` | text | |
| `metadata` | jsonb | |

### 4.3. `farm.tasks`

**Purpose:** the resumable work queue. This is the table that turns "the farm got interrupted" from
a disaster into a non-event.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `task_id` | text, unique | |
| `run_id` | text, FK → `runs.run_id` | |
| `task_type` | text | |
| `prompt` | text | |
| `input_payload` | jsonb | |
| `expected_schema` | jsonb | what the Selector will validate the output against |
| `status` | text | `pending`, `generating`, `generated`, `validating`, `accepted`, `rejected`, `failed`, `paused` |
| `priority` | int, default 0 | |
| `created_at`, `updated_at` | timestamptz | |
| `metadata` | jsonb | |

### 4.4. `farm.generations`

**Purpose:** the raw output of a model for a task. Deliberately holds **no lifecycle/status
column** — whether a generation was ultimately accepted or rejected is recorded once, in
`validation_results` / `samples`, not duplicated here. A generation is just "what came out of the
model", full stop.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `generation_id` | text, unique | |
| `task_id` | text, FK → `tasks.task_id` | |
| `run_id` | text, FK → `runs.run_id` | |
| `model_id` | text, FK → `model_registry.model_id` | |
| `temperature` | numeric | |
| `raw_output` | text | |
| `parsed_output` | jsonb, nullable | null if parsing failed |
| `latency_ms` | int | |
| `created_at` | timestamptz | |
| `metadata` | jsonb | |

### 4.5. `farm.validation_results`

**Purpose:** the verdict, and — critically — *why*. This is what makes `datasets/rejected/` useful
for debugging prompts and validators instead of being a black hole.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `validation_id` | text, unique | |
| `generation_id` | text, FK → `generations.generation_id` | |
| `validator_version` | text | |
| `is_valid` | bool | |
| `score` | numeric, nullable | |
| `failure_code` | text, nullable | `invalid_json`, `schema_error`, `missing_field`, `wrong_type`, `nan_detected`, `infinity_detected`, `range_error`, `logic_error`, `duplicate_sample`, `empty_output`, `too_long_output` |
| `failure_reason` | text, nullable | human-readable detail |
| `validation_details` | jsonb, nullable | |
| `created_at` | timestamptz | |

### 4.6. `farm.samples` (merged golden + rejected)

**Purpose:** the final disposition of a generation — accepted into the golden set, or rejected.
The original draft plan had two near-identical tables (`golden_samples`, `rejected_samples`)
sharing 8 of 10 columns; merging them into one table with a `status` column removes that
duplication and the risk of the two tables' schemas silently drifting apart over time.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `sample_id` | text, unique | |
| `validation_result_id` | text, FK → `validation_results.validation_id` | |
| `task_id` | text, FK → `tasks.task_id` | |
| `generation_id` | text, FK → `generations.generation_id` | |
| `run_id` | text, FK → `runs.run_id` | |
| `model_id` | text, FK → `model_registry.model_id` | |
| `dataset_id` | text, nullable | **label only, no FK** — see §9.2 |
| `status` | text | `accepted`, `rejected` |
| `prompt`, `completion` | text | |
| `failure_code`, `failure_reason` | text, nullable | populated only when `status = 'rejected'` |
| `score` | numeric, nullable | |
| `selector_version` | text | |
| `created_at` | timestamptz | |
| `metadata` | jsonb | |

### 4.7. `farm.embeddings`

**Purpose:** vectors for pgvector-based deduplication and similarity search — required from v001
because deduplication is an explicit Selector responsibility
(`selection_farm_project_structure_guide.md`, §4.1).

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `embedding_id` | text, unique | |
| `source_type` | text | `task`, `generation`, `sample` |
| `source_id` | text | id of the row in the corresponding table (polymorphic — no FK, discriminated by `source_type`) |
| `embedding_model_id` | text | e.g. `nomic-embed-text` |
| `embedding` | `vector(768)` | dimension matches `nomic-embed-text`; revisit if the embedding model changes |
| `created_at` | timestamptz | |
| `metadata` | jsonb | |

---

## 5. Data flow

```text
model_registry
      │
      ▼
runs
      │
      ▼
tasks  ──────────────┐
      │               │ (dedup check before generating)
      ▼               ▼
generations  ◄────  embeddings
      │
      ▼
validation_results
      │
      ├── is_valid = true  → samples (status = accepted) → datasets/golden/*.jsonl (export)
      └── is_valid = false → samples (status = rejected) → datasets/rejected/*.jsonl (export)
```

---

## 6. Minimal Selector SQL flow

Concrete write sequence for one task going through the Selector, so the tables in §4 read as a
pipeline rather than an abstract diagram:

```text
1. INSERT INTO farm.runs (run_id, run_type='selector', status='running', ...)
2. INSERT INTO farm.tasks (task_id, run_id, status='pending', ...)        -- from tasks.jsonl import
3. SELECT * FROM farm.tasks WHERE status = 'pending' ORDER BY priority LIMIT 1
4. UPDATE farm.tasks SET status = 'generating' WHERE task_id = ...
5. -- call Ollama --
6. INSERT INTO farm.generations (generation_id, task_id, run_id, model_id, raw_output, ...)
7. UPDATE farm.tasks SET status = 'validating' WHERE task_id = ...
8. -- run validators (schema, range, NaN/Inf, JSON) --
9. INSERT INTO farm.validation_results (validation_id, generation_id, is_valid, failure_code, ...)
10. -- if is_valid: embed the output, check for near-duplicates via pgvector --
11. INSERT INTO farm.embeddings (embedding_id, source_type='generation', source_id=generation_id, ...)
12. INSERT INTO farm.samples (sample_id, validation_result_id, ..., status = 'accepted' | 'rejected')
13. UPDATE farm.tasks SET status = 'accepted' | 'rejected' WHERE task_id = ...
14. UPDATE farm.runs SET processed_items = processed_items + 1,
                          accepted_items = accepted_items + (1 if accepted else 0),
                          rejected_items = rejected_items + (1 if rejected else 0)
    WHERE run_id = ...
15. -- repeat from step 3 until no pending tasks remain --
16. UPDATE farm.runs SET status = 'completed', finished_at = now() WHERE run_id = ...
```

Step 3 is also exactly what makes resume-after-interruption work: on restart, the same query
(`WHERE status = 'pending'`, plus picking up anything left at `'generating'`/`'validating'` from
a crash) is the entire recovery logic — no separate checkpoint mechanism needed.

---

## 7. Required indexes (v001)

```sql
CREATE UNIQUE INDEX ON farm.model_registry (model_id);
CREATE INDEX ON farm.model_registry (status);

CREATE INDEX ON farm.runs (run_type);
CREATE INDEX ON farm.runs (status);
CREATE INDEX ON farm.runs (started_at);

CREATE INDEX ON farm.tasks (status);
CREATE INDEX ON farm.tasks (run_id);

CREATE INDEX ON farm.generations (task_id);
CREATE INDEX ON farm.generations (run_id);
CREATE INDEX ON farm.generations (model_id);

CREATE INDEX ON farm.validation_results (generation_id);
CREATE INDEX ON farm.validation_results (is_valid);
CREATE INDEX ON farm.validation_results (failure_code);

CREATE INDEX ON farm.samples (status);
CREATE INDEX ON farm.samples (model_id);
CREATE INDEX ON farm.samples (dataset_id);
CREATE INDEX ON farm.samples (run_id);

CREATE INDEX ON farm.embeddings USING hnsw (embedding vector_cosine_ops);
```

The HNSW index is only worth building once there are a meaningful number of embeddings (hundreds+).
It's harmless to create early, but don't expect — or need — it to matter at a few dozen rows.

---

## 8. Explicitly out of scope for v001

Not tables to avoid forever — just tables that don't earn their complexity yet, per the project's
own "install only what supports the current stage" rule:

```text
farm.model_lineage      → needs at least a second model / an actual breeding decision to be
                           meaningful. Zero models exist right now. Use
                           studbook/model_lineage/lineage.yaml (already scaffolded) until then.

farm.datasets            → see §9.2 in detail. The file-based dataset card already covers this,
                           and a DB table would duplicate it with no consumer yet.

farm.bereiter_trials,
farm.bereiter_trial_results,
farm.training_jobs,
farm.model_promotions    → all belong once Bereiter/Trainer are actually being built. Adding them
                           now means guessing at columns for code that doesn't exist yet.
```

---

## 9. Database vs. files — who owns what

This is the concrete application of the "one source of truth" rule from §1.2.

### 9.1. Model registry vs. model passport

`farm.model_registry` (DB) and `studbook/model_registry/models/<model_id>.yaml` (file,
mandated by `PROJECT_PHILOSOPHY.md` §9) describe overlapping facts. To avoid two hand-maintained
copies:

```text
farm.model_registry           = source of truth, updated by code (Selector/Bereiter/Trainer)
studbook/model_registry/*.yaml = generated snapshot, exported FROM the DB row for human reading
```

Status transitions to `worker_model` / `breeding_model` still require a recorded decision, per
philosophy — that decision lives in `studbook/breeding_decisions/` /
`studbook/worker_admissions/` (file-based, human-authored, append-only) and is what triggers the
`model_registry.status` update, not the other way around.

### 9.2. Dataset identity vs. dataset registry

No `farm.datasets` table in v001. `datasets/golden/dataset_card_v001.md` and `checksums.txt`
remain the only record of a dataset version. `runs.dataset_id` and `samples.dataset_id` are plain
text labels — enough for traceability ("which dataset was this run against") without a second
table to keep in sync.

The implemented `scripts/export_golden_dataset.sh` follows this flow independently for the LLM and
ML dataset identities:

```text
SELECT joined evidence FROM farm.samples WHERE status = ... AND dataset_id = ...
      → branch-owned serializer
      → atomically replace distinct accepted/rejected LLM and ML JSONL exports
```

i.e. the dataset card is a **generated export**, not something edited by hand in parallel with the
database. This is exactly why a `farm.datasets` table isn't needed yet: the DB already has
everything the export needs, and the file is the artifact, not a second registry.

### 9.3. Golden/rejected samples vs. `farm.samples`

Not a duplication in the same sense — the two representations do different jobs:

```text
farm.samples              = operational tracking: dedup lookups, resumability, cross-run reporting
datasets/golden/*.jsonl    = the portable, git-trackable artifact Trainer actually reads to train
```

`datasets/golden/*.jsonl` is produced by exporting from `farm.samples` (§9.2), not maintained
independently.

---

## 10. Acceptance criteria for v001

```text
1.  postgres container starts without errors (already verified — see stack guide)
2.  pgvector extension is active (already verified — v0.5.1)
3.  db/schema.sql applies without errors
4.  all farm.* tables from §3 exist
5.  all indexes from §7 exist
6.  can insert a test row into farm.model_registry
7.  can insert a test row into farm.runs referencing that model
8.  can insert a test row into farm.tasks referencing that run
9.  can insert a test row into farm.generations referencing that task
10. can insert a test row into farm.validation_results referencing that generation
11. can insert a test row into farm.samples referencing that validation_result
12. can insert a vector(768) into farm.embeddings
13. can run a cosine similarity query against farm.embeddings
14. tests/integration/test_postgres_connection.py passes
15. tests/integration/test_pgvector_dedup.py passes
```

---

## Agent operating rules

## 1. One fact, one owner

Before adding a column to a table, check whether that fact already has a file-based home per §9.
If it does, don't duplicate it — export to the file, don't hand-maintain both.

## 2. Don't let `metadata` become a second schema

`metadata jsonb` is an escape hatch for genuinely unstructured, rarely-queried detail. If a field
gets queried or joined on, it belongs as a real column with an index, not buried in `metadata`.

## 3. Migrations are additive

Never edit an already-applied migration file. A schema change is a new file:
`<next_number>_<description>.sql` (the next free number after §2's `006`). `db/schema.sql` is
then regenerated to match.

## 4. `generations` never carries a lifecycle status

Disposition (accepted/rejected, and why) lives in `validation_results` and `samples`. Adding a
status column back onto `generations` re-creates the three-places-tracking-the-same-fact problem
this schema was designed to avoid.

## 5. `dataset_id` is a label, not a foreign key, until §9.2 says otherwise

Don't add a `farm.datasets` table opportunistically while implementing something else. Revisit
only when a concrete cross-dataset query need shows up.

## Final principle

The database is the operational memory of the farm — resumable state, dedup, and joins. The
studbook and dataset files are its curated, human-facing record. Neither should silently drift
from the other; where they overlap, one is generated from the other, on purpose, by name.
