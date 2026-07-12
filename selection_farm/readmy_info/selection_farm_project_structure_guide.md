# Selection Farm — Project Structure Guide

## Purpose of this document

This document is a context map and onboarding guide for agents working on the **Selection Farm** project.

The project is designed as a local model selection and training farm. Its goal is to work with small, resource-efficient models, train or fine-tune them for narrow tasks, evaluate generations, select breeding models, and export worker models into resource-limited production pipelines.

The project uses the horse breeding analogy as a conceptual map:

```text
Stable      = model storage and classification area
Studbook    = model registry, lineage, decisions, and history
Selector    = strict answer/data selection layer
Bereiter    = model trial and skill evaluation layer
Trainer     = training/fine-tuning layer
Worker      = model approved for production pipeline
Breeding    = model approved for further generations
```

Important project rule:

```text
Models must be small, fast, and resource-efficient.
Heavy models are not allowed in the main pipeline without explicit technical justification.
```

---

## Top-level project block scheme

```text
selection_farm/
├── stable/          # Model stables: artifacts, adapters, statuses, model cards
├── studbook/        # Breeding book: registry, lineage, reports, decisions
├── datasets/        # Raw, golden, rejected, and evaluation datasets
├── services/        # Source code for Selector, Bereiter, Trainer
├── db/              # Database schema, migrations, SQL definitions
├── configs/         # YAML/TOML/JSON configs for models, runs, eval, training
├── logs/            # Runtime logs and diagnostic output
├── tests/           # Unit, integration, validation, and regression tests
├── scripts/         # Utility scripts and operational commands
├── docker/          # Docker Compose, Dockerfiles, container env examples
├── .vscode/         # VS Code workspace settings
├── .gitignore       # Git ignore rules
├── Makefile         # Short project commands
├── pyproject.toml   # Python tooling configuration
└── README.md        # Main project overview
```

---

# 1. `stable/`

## Role

`stable/` is the model stable. It stores model-related artifacts, adapters, lightweight exported models, model cards, evaluation summaries, and status files.

It should not blindly duplicate large model weights already stored by Ollama or external model caches.

## Block scheme

```text
stable/
├── llm_models_stall/
├── ml_models_stall/
├── hybrid_models_stall/
├── breeding_models/
├── worker_models/
├── rejected_models/
└── archived_models/
```

## 1.1. `stable/llm_models_stall/`

### Purpose

Stores metadata and artifacts for LLM models:

```text
Qwen
Llama
Gemma
Phi
DeepSeek Distill
small judge models
small reasoning models
embedding models when managed as LLM assets
```

### Expected files

```text
stable/llm_models_stall/<model_name>/
├── model_card.md
├── base_info.yaml
├── adapters/
├── eval_reports/
├── prompts/
└── status.yaml
```

### File purposes

| File / Directory | Purpose |
|---|---|
| `model_card.md` | Human-readable model description, intended role, limitations |
| `base_info.yaml` | Base model name, source, license, size, quantization, family |
| `adapters/` | LoRA/QLoRA adapters created during fine-tuning |
| `eval_reports/` | Evaluation reports for this model |
| `prompts/` | Prompt templates used with this model |
| `status.yaml` | Current status: raw, trained, tested, breeding, worker, rejected |

---

## 1.2. `stable/ml_models_stall/`

### Purpose

Stores classical ML models and narrow task-specific models.

Examples:

```text
LightGBM
XGBoost
CatBoost
RandomForest
LogisticRegression
IsolationForest
small neural networks
ranking models
scoring models
```

### Expected files

```text
stable/ml_models_stall/<model_name>/
├── model.pkl
├── model.joblib
├── model.onnx
├── features.yaml
├── training_config.yaml
├── eval_report.json
├── model_card.md
└── status.yaml
```

### File purposes

| File | Purpose |
|---|---|
| `model.pkl` / `model.joblib` | Serialized Python ML model |
| `model.onnx` | Optional portable inference export |
| `features.yaml` | Exact feature list and feature order |
| `training_config.yaml` | Training parameters |
| `eval_report.json` | Metrics and validation results |
| `model_card.md` | Human-readable model description |
| `status.yaml` | Current production/breeding/rejection status |

---

## 1.3. `stable/hybrid_models_stall/`

### Purpose

Stores hybrid model pipelines where different model types work together.

Examples:

```text
ML model + LLM explanation
Scorer + JSON formatter
Embedding search + LLM reasoning
Classifier + LLM report generator
```

### Expected files

```text
stable/hybrid_models_stall/<hybrid_name>/
├── pipeline.yaml
├── components.yaml
├── integration_notes.md
├── eval_report.json
└── status.yaml
```

### File purposes

| File | Purpose |
|---|---|
| `pipeline.yaml` | Defines component order and data flow |
| `components.yaml` | Lists ML/LLM/embedding models used |
| `integration_notes.md` | Explains how the hybrid system is used |
| `eval_report.json` | Hybrid pipeline evaluation metrics |
| `status.yaml` | Current lifecycle status |

---

## 1.4. `stable/breeding_models/`

### Purpose

Stores references and artifacts for models approved for further generations.

A breeding model is not necessarily production-ready. It is a strong candidate for further training, merging, or data generation.

### Expected files

```text
stable/breeding_models/
├── approved_breeding_models.yaml
├── candidates/
└── notes.md
```

### File purposes

| File / Directory | Purpose |
|---|---|
| `approved_breeding_models.yaml` | List of models approved for further evolution |
| `candidates/` | Candidate breeding model references |
| `notes.md` | Manual notes and rationale |

---

## 1.5. `stable/worker_models/`

### Purpose

Stores models approved for integration into production or working pipelines.

A worker model must be lightweight, tested, and resource-efficient.

### Expected files

```text
stable/worker_models/
├── production_ready/
├── staging/
└── worker_registry.yaml
```

### File purposes

| File / Directory | Purpose |
|---|---|
| `production_ready/` | Models approved for real pipeline usage |
| `staging/` | Models under final integration testing |
| `worker_registry.yaml` | Worker model registry and metadata |

---

## 1.6. `stable/rejected_models/`

### Purpose

Stores records for rejected models.

Rejected models are not deleted immediately. Their failure reasons are preserved to avoid repeating bad experiments.

### Expected files

```text
stable/rejected_models/
├── rejected_registry.yaml
├── failure_reports/
└── notes.md
```

### File purposes

| File / Directory | Purpose |
|---|---|
| `rejected_registry.yaml` | List of rejected models |
| `failure_reports/` | Detailed rejection reports |
| `notes.md` | General rejection observations |

---

## 1.7. `stable/archived_models/`

### Purpose

Stores old, inactive, or superseded models.

Archived models are preserved for history but are not active in selection or production.

### Expected files

```text
stable/archived_models/
├── archive_index.yaml
└── archived_reports/
```

---

# 2. `studbook/`

## Role

`studbook/` is the breeding book of the project.

It stores model registry, lineage, generation history, selection decisions, worker admissions, and rejection reports.

It is the memory of the model farm.

## Block scheme

```text
studbook/
├── model_registry/
├── model_lineage/
├── generation_reports/
├── breeding_decisions/
├── worker_admissions/
├── rejected_reports/
└── templates/
```

---

## 2.1. `studbook/model_registry/`

### Purpose

Stores model registry records.

### Expected files

```text
studbook/model_registry/
├── registry.yaml
├── registry.jsonl
└── models/
    └── <model_id>.yaml
```

### File purposes

| File | Purpose |
|---|---|
| `registry.yaml` | Human-readable model registry |
| `registry.jsonl` | Machine-readable append-only registry |
| `models/<model_id>.yaml` | Individual model passport |

### Model passport example

```yaml
model_id: MO000000
model_name: qwen3_0_6b_candidate
model_type: llm
base_model: qwen3:0.6b
resource_class: 0.6b_1b
generation:
parent_model_id:
status: trained_candidate
allowed_for_pipeline: false
allowed_for_breeding: true
created_at:
updated_at:
metadata: {}
```

---

## 2.2. `studbook/model_lineage/`

### Purpose

Stores parent-child relationships between models and generations.

### Expected files

```text
studbook/model_lineage/
├── lineage.yaml
├── lineage_graph.mmd
└── lineage_events.jsonl
```

### File purposes

| File | Purpose |
|---|---|
| `lineage.yaml` | Structured parent/child model lineage |
| `lineage_graph.mmd` | Mermaid graph of model lineage |
| `lineage_events.jsonl` | Append-only lineage event log |

---

## 2.3. `studbook/generation_reports/`

### Purpose

Stores reports for each generation cycle.

### Expected files

```text
studbook/generation_reports/
└── generation_001/
    ├── summary.md
    ├── metrics.json
    ├── selector_stats.json
    ├── bereiter_stats.json
    └── decision.md
```

### File purposes

| File | Purpose |
|---|---|
| `summary.md` | Human-readable generation summary |
| `metrics.json` | Numeric generation metrics |
| `selector_stats.json` | Selector performance stats |
| `bereiter_stats.json` | Trial/evaluation stats |
| `decision.md` | Decision: continue, breed, worker, reject, archive |

---

## 2.4. `studbook/breeding_decisions/`

### Purpose

Stores formal decisions that approve models for further evolution.

### Expected files

```text
studbook/breeding_decisions/
├── breeding_decision_<model_id>.md
└── breeding_decisions.jsonl
```

### File purposes

| File | Purpose |
|---|---|
| `breeding_decision_<model_id>.md` | Human-readable decision explanation |
| `breeding_decisions.jsonl` | Machine-readable decision log |

---

## 2.5. `studbook/worker_admissions/`

### Purpose

Stores approval records for models admitted into production or working pipelines.

### Expected files

```text
studbook/worker_admissions/
├── worker_admission_<model_id>.md
└── worker_admissions.jsonl
```

### File purposes

| File | Purpose |
|---|---|
| `worker_admission_<model_id>.md` | Explanation why model is production-ready |
| `worker_admissions.jsonl` | Machine-readable worker approval log |

---

## 2.6. `studbook/rejected_reports/`

### Purpose

Stores rejection reports for failed models.

### Expected files

```text
studbook/rejected_reports/
├── rejected_<model_id>.md
└── rejected_models.jsonl
```

### File purposes

| File | Purpose |
|---|---|
| `rejected_<model_id>.md` | Human-readable rejection reason |
| `rejected_models.jsonl` | Machine-readable rejection log |

---

## 2.7. `studbook/templates/`

### Purpose

Stores reusable templates for reports and model records.

### Expected files

```text
studbook/templates/
├── model_card_template.md
├── model_passport_template.yaml
├── generation_report_template.md
├── breeding_decision_template.md
├── worker_admission_template.md
└── rejection_report_template.md
```

---

# 3. `datasets/`

## Role

`datasets/` stores data used for selection, training, rejection analysis, and evaluation.

## Block scheme

```text
datasets/
├── raw/
├── golden/
├── rejected/
└── eval/
```

---

## 3.1. `datasets/raw/`

### Purpose

Stores raw input data and raw task files.

### Expected files

```text
datasets/raw/
├── tasks.jsonl
├── source_data/
└── README.md
```

### Rules

Raw data should not be edited manually after being added. If cleaned data is needed, create a new derived dataset.

---

## 3.2. `datasets/golden/`

### Purpose

Stores selected high-quality training examples.

Only data accepted by the Selector should enter this directory.

### Expected files

```text
datasets/golden/
├── golden_dataset_v001.jsonl
├── golden_dataset_v002.jsonl
├── dataset_card_v001.md
└── checksums.txt
```

### Rules

A golden dataset must include:

```text
dataset_id
selector_version
source_run_id
creation_date
validation rules
known limitations
```

---

## 3.3. `datasets/rejected/`

### Purpose

Stores rejected generations and reasons for rejection.

### Expected files

```text
datasets/rejected/
├── rejected_v001.jsonl
├── rejection_summary.md
└── rejection_stats.json
```

### Purpose of rejected data

Rejected data is useful for:

```text
debugging prompts
improving validators
identifying weak model behavior
preventing repeated errors
```

---

## 3.4. `datasets/eval/`

### Purpose

Stores evaluation datasets.

Evaluation data must be separated from training data.

### Expected files

```text
datasets/eval/
├── holdout_eval_v001.jsonl
├── regression_eval_v001.jsonl
├── stress_eval_v001.jsonl
└── eval_card.md
```

### Rules

Do not train on evaluation datasets.

---

# 4. `services/`

## Role

`services/` stores source code for the main logical services of the farm.

## Block scheme

```text
services/
├── selector/
├── bereiter/
└── trainer/
```

---

## 4.1. `services/selector/`

### Purpose

The Selector is the strict quality gate.

It validates model outputs, rejects bad samples, accepts high-quality samples, and writes selection results.

### Expected files

```text
services/selector/
├── app/
│   ├── core/             # branch-neutral orchestration and infrastructure contracts
│   ├── llm/              # LLM-only composition, validation, dedup, and export
│   └── ml/               # ML-only inference, validation, dedup, and export
├── requirements.txt
└── README.md
```

Allowed dependency direction:

```text
llm  ──────> core <────── ml
```

`core` may not import either branch, and `llm`/`ml` may not import one another. Every new package
directory has a local `README.md`; `tests/integration/test_selector_architecture.py` enforces the
dependency boundary. The obsolete flat Selector modules are not a compatibility API.

The LLM branch resolves the complete v001 component profile through an explicit allowlist before a
run may be created. Its current reference composition is `single_turn` + `ollama` + `text`.
Provider calls use httpx against non-streaming `/api/generate` and `/api/embed`; transport timeouts,
two-attempt transient retry, typed responses, and exact finite 768-dimensional embeddings are
enforced inside the LLM runtime without a database transaction or provider SDK.
The v001 LLM result path uses a registered strict structured-JSON contract followed by Draft
2020-12 schema validation and same-dataset accepted-sample pgvector deduplication. Invalid JSON or
schema output never triggers embedding, and semantic distance at or below the configured threshold
is rejected as a duplicate.
The ML branch resolves only explicit registered `pipeline_id` values. Its v001 reference adapter
loads trusted local `.joblib` estimators, prepares features in config order, requires `predict`, and
uses `predict_proba` only when the classification confidence contract requires it. No model-family
name inference or dispatch chain exists in the producer.
ML decisions then pass explicit class/range/probability/confidence validation before exact input
duplicate lookup. The canonical input is the strictly typed feature object with deterministic key
order; accepted comparisons are limited to the same ML dataset and never use semantic distance.
Committed DB samples are published through branch-owned LLM/ML serializers into four distinct
accepted/rejected JSONL files. Core stages every payload before a rollback-capable atomic replace;
generated datasets are never a parallel hand-maintained source of truth.
The neutral Core pipeline receives one explicit assembled branch, checks the exact registered model
type before creating a run, persists resumable checkpoints, and atomically accounts for terminal
task outcomes. Separate CWD-independent LLM and ML scripts use the workspace venv; the common
dispatcher requires `--branch llm` or `--branch ml` and performs no auto-detection.
Task 13 verifies this assembly against live PostgreSQL with temporary LLM/ML registry rows, an
injected LLM provider, and a pytest-owned joblib/sklearn artifact. Both branches persist isolated
accepted evidence and distinct DB-first exports with exact counters; cleanup leaves zero `_tz08_`
rows/files and does not touch production ID counters. Installed Ollama structured generation is
healthy, while the absent approved embedding model keeps fully live LLM E2E explicitly
inconclusive without pull or fallback.

### Responsibilities

```text
coordinate resumable DB-first evaluation through Core
run LLM generation, structured validation, and semantic dedup in the LLM branch
run typed estimator inference, ML validation, and exact dedup in the ML branch
publish branch-owned golden and rejected exports from committed DB evidence
```

---

## 4.2. `services/bereiter/`

### Purpose

The Bereiter is the model trial manager.

It tests models under practical working scenarios and determines whether they are suitable as worker, breeding, training, or rejected models.

### Expected files

```text
services/bereiter/
├── app/
│   ├── main.py
│   ├── trial_runner.py
│   ├── metrics.py
│   ├── resource_monitor.py
│   ├── report_writer.py
│   └── config.py
├── requirements.txt
└── README.md
```

### Responsibilities

```text
run evaluation trials
measure accuracy
measure JSON stability
measure latency
measure RAM usage
compare with previous generations
produce admission or rejection reports
```

---

## 4.3. `services/trainer/`

### Purpose

The Trainer handles fine-tuning and training workflows.

It should support lightweight training only, especially LoRA/QLoRA or classical ML training.

### Expected files

```text
services/trainer/
├── app/
│   ├── main.py
│   ├── train_llm_lora.py
│   ├── train_ml_model.py
│   ├── export_model.py
│   ├── checkpoint_manager.py
│   └── config.py
├── requirements.txt
└── README.md
```

### Responsibilities

```text
train LoRA/QLoRA adapters
train classical ML models
save checkpoints
resume interrupted training
export models
write training metadata
```

---

# 5. `db/`

## Role

`db/` stores database definitions, migrations, and SQL-related project files.

The actual PostgreSQL data directory should not be committed to Git.

## Expected files

```text
db/
├── init.sql
├── schema.sql
├── migrations/
│   ├── 001_init.sql
│   ├── 002_add_pgvector.sql
│   └── 003_model_registry.sql
└── README.md
```

## Responsibilities

```text
define PostgreSQL schema
define pgvector extension
define model registry tables
define run tracking tables
define generation result tables
define indexes
```

---

# 6. `configs/`

## Role

`configs/` stores configuration files for selection, training, evaluation, models, and environment-specific runs.

## Expected files

```text
configs/
├── selector/
│   └── selector_v001.yaml
├── bereiter/
│   └── trial_config_v001.yaml
├── trainer/
│   └── lora_train_v001.yaml
├── models/
│   └── model_profiles.yaml
├── datasets/
│   └── dataset_profiles.yaml
└── README.md
```

## Rules

Configuration changes must be versioned. Do not silently overwrite old config files used in previous runs.

---

# 7. `logs/`

## Role

`logs/` stores runtime logs.

Logs are useful for debugging but may grow quickly. Large logs should not be committed to Git.

## Expected files

```text
logs/
├── selector.log
├── bereiter.log
├── trainer.log
├── docker/
└── archived/
```

## Rules

```text
Keep logs local by default.
Archive important logs into studbook reports when needed.
Do not commit large runtime logs.
```

---

# 8. `tests/`

## Role

`tests/` stores automated tests.

Tests protect the farm from silent degradation.

## Expected files

```text
tests/
├── unit/
│   ├── test_selector_validators.py
│   ├── test_schemas.py
│   └── test_dataset_writer.py
├── integration/
│   ├── test_ollama_connection.py
│   ├── test_postgres_connection.py
│   └── test_pgvector_dedup.py
├── regression/
│   └── test_generation_regression.py
└── README.md
```

## Required test categories

```text
JSON validation tests
schema validation tests
empty input tests
NaN/Inf tests
range tests
duplicate detection tests
database write tests
resume-after-interruption tests
```

---

# 9. `scripts/`

## Role

`scripts/` stores operational helper scripts.

Scripts should be small, explicit, and safe.

## Expected files

```text
scripts/
├── create_project_tree.sh
├── run_selector.sh
├── run_selector_llm.sh
├── run_selector_ml.sh
├── run_bereiter.sh
├── run_trainer.sh
├── export_golden_dataset.sh
├── backup_studbook.sh
├── cleanup_logs.sh
└── README.md
```

## Rules

Scripts must not silently delete important data.

Any destructive script must require explicit confirmation.

---

# 10. `docker/`

## Role

`docker/` stores all Docker-related files.

Docker files are separated from source code to keep the project structure clean.

## Expected files

```text
docker/
├── docker-compose.yml
├── .env.example
├── .env
├── postgres/
│   └── init.sql
├── selector/
│   └── Dockerfile
├── bereiter/
│   └── Dockerfile
└── trainer/
    └── Dockerfile
```

## Rules

```text
docker/.env must not be committed to Git.
docker/.env.example should be committed.
Docker volumes should point to project directories intentionally.
Do not mount random host paths.
```

## Example commands

From project root:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d
docker compose -f docker/docker-compose.yml --env-file docker/.env down
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f
```

---

# 11. `.vscode/`

## Role

`.vscode/` stores VS Code project settings.

VS Code is used inside Debian 13 VM as the project IDE.

## Expected files

```text
.vscode/
├── settings.json
├── launch.json
└── tasks.json
```

## File purposes

| File | Purpose |
|---|---|
| `settings.json` | Formatting, linting, Python interpreter, editor rules |
| `launch.json` | Debug configurations |
| `tasks.json` | Run selector, tests, Docker commands from VS Code |

---

# 12. `.gitignore`

## Role

Defines files that must not be committed.

## Must ignore

```text
docker/.env
logs/*
*.log
__pycache__/
.venv/
*.pyc
datasets/raw/private/
datasets/rejected/*.jsonl
stable/**/large_weights/
data/
*.gguf
*.safetensors
*.bin
```

Do not ignore templates, configs, small model cards, or report files.

---

# 13. `Makefile`

## Role

Provides short commands for common operations.

## Expected commands

```text
make up
make down
make logs
make ps
make test
make selector
make bereiter
make trainer
make backup
```

The Makefile should call Docker Compose using files from `docker/`.

---

# 14. `pyproject.toml`

## Role

Stores Python project configuration.

## Expected tools

```text
ruff
black
pytest
mypy optional
coverage optional
```

## Purpose

```text
consistent formatting
linting
test discovery
project metadata
```

---

# 15. `README.md`

## Role

Main project entry point.

## Expected content

```text
project purpose
hardware assumptions
resource limits
core principles
quick start
directory map
main commands
current roadmap
```

---

# Agent operating rules

## 1. Do not mix responsibilities

```text
services/ = code
datasets/ = data
stable/ = model artifacts
studbook/ = model history and decisions
configs/ = configuration
docker/ = infrastructure
logs/ = runtime logs
tests/ = automated checks
```

## 2. Do not train on rejected or eval data

```text
datasets/rejected/ is for analysis only.
datasets/eval/ is for evaluation only.
Only datasets/golden/ may be used for training.
```

## 3. Do not overwrite lineage

Model lineage and generation reports must be append-only whenever possible.

## 4. Do not use heavy models without justification

The farm is designed for resource-limited deployment.

Preferred model range:

```text
0.6B–1B  = fast experiments
1.5B–1.7B = main working range
3B = upper normal range
4B = occasional judge/evaluator
7B+ = rare benchmark only
```

## 5. Every model must have a passport

No model is allowed into breeding or worker status without:

```text
model_id
model_name
model_type
base_model
resource_class
generation
parent_model_id
status
allowed_for_pipeline
allowed_for_breeding
created_at
updated_at
metadata
```

Run-specific fields (`dataset_id`, `training_config_id`, `selector_version`, metrics and resource
usage) are recorded in runtime tables or generated reports, not in the model passport. Decision
reasons are recorded in `studbook/breeding_decisions/` or `studbook/worker_admissions/`.

## 6. Every generation must have a report

Each generation cycle must produce:

```text
summary.md
metrics.json
selector_stats.json
bereiter_stats.json
decision.md
```

## 7. Interruption must be safe

Long-running processes must support:

```text
status tracking
checkpoints
resume
logs
partial result saving
```

## Final principle

The Selection Farm is not a collection of random models.

It is a controlled breeding and testing system for small, specialized, resource-efficient models.

The goal is to produce reliable worker models for real pipelines and preserve strong breeding models for future generations.
