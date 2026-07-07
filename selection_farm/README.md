# Selection Farm

## Project purpose

Selection Farm is a local model selection, training, and evaluation project.

Its goal is to create and manage small, specialized, resource-efficient models for use in limited-resource production pipelines.

The project supports:

```text
LLM fine-tuning
classical ML model training
hybrid ML + LLM pipelines
model evaluation
model lineage tracking
golden dataset generation
worker model admission
breeding model selection
```

---

## Main rule

```text
Models must be lightweight and resource-efficient.
```

The target environment is resource-limited.  
The project must not depend on large models unless there is a clear technical reason.

Preferred model range:

```text
0.6B–1B     = fast tests
1.5B–1.7B  = main working range
3B         = upper normal range
4B         = judge/evaluator only when needed
7B+        = rare benchmark only
```

---

## Current working environment

The current project environment is:

```text
Windows 11 Pro host
VMware Workstation Pro
Debian 13 VM
CPU-first / CPU-only AI execution
VS Code inside Debian 13
Docker inside Debian 13
```

The project must be designed to work safely even if sessions are interrupted.

---

## Top-level structure

```text
selection_farm/
├── stable/
│   ├── llm_models_stall/
│   ├── ml_models_stall/
│   ├── hybrid_models_stall/
│   ├── breeding_models/
│   ├── worker_models/
│   ├── rejected_models/
│   └── archived_models/
│
├── studbook/
│   ├── model_registry/
│   ├── model_lineage/
│   ├── generation_reports/
│   ├── breeding_decisions/
│   ├── worker_admissions/
│   ├── rejected_reports/
│   └── templates/
│
├── datasets/
│   ├── raw/
│   ├── golden/
│   ├── rejected/
│   └── eval/
│
├── services/
│   ├── selector/
│   ├── bereiter/
│   └── trainer/
│
├── db/
├── configs/
├── logs/
├── tests/
├── scripts/
├── docker/
├── .vscode/
├── .gitignore
├── Makefile
├── pyproject.toml
└── README.md
```

---

## Directory roles

| Directory | Purpose |
|---|---|
| `stable/` | Model artifacts, adapters, model cards, worker/breeding/rejected status areas |
| `studbook/` | Model registry, lineage, generation reports, admission/rejection decisions |
| `datasets/` | Raw, golden, rejected, and evaluation datasets |
| `services/` | Source code for Selector, Bereiter, and Trainer |
| `db/` | SQL schemas, migrations, PostgreSQL and pgvector definitions |
| `configs/` | YAML/TOML/JSON configs for training, selection, evaluation, models |
| `logs/` | Runtime logs and diagnostics |
| `tests/` | Unit, integration, regression, and validation tests |
| `scripts/` | Operational helper scripts |
| `docker/` | Docker Compose, Dockerfiles, container environment examples |
| `.vscode/` | VS Code workspace settings |
| `Makefile` | Short project commands |
| `pyproject.toml` | Python tooling configuration |

---

## Core components

### Python Selector

Strict selection layer.

Responsibilities:

```text
validate JSON
validate schemas
validate numeric ranges
reject bad generations
accept good samples
deduplicate with embeddings
write golden datasets
write rejected datasets
record run metadata
```

### Bereiter

Model trial and preparation layer.

Responsibilities:

```text
run trials
measure accuracy
measure latency
measure RAM usage
measure JSON stability
compare generations
recommend model status
write reports
```

### Trainer

Training and fine-tuning layer.

Responsibilities:

```text
train classical ML models
train LoRA/QLoRA adapters
save checkpoints
resume interrupted training
export models
write training metadata
```

---

## Model lines

### LLM line

```text
ready small open-source LLM
→ fine-tuning / LoRA / QLoRA
→ evaluation
→ worker_model or breeding_model
```

LLMs are used for:

```text
text understanding
structured JSON output
explanations
log analysis
prompt transformation
reasoning over messy inputs
```

### ML line

```text
own data
→ features
→ training from scratch
→ evaluation
→ worker_model
```

ML models are used for:

```text
buy/sell/hold classification
scoring
ranking
risk estimation
anomaly detection
tabular decision logic
```

### Hybrid line

```text
ML model decides
LLM explains or formats
Selector validates
Pipeline consumes output
```

---

## Model lifecycle statuses

```text
raw_candidate
trained_candidate
tested_candidate
breeding_model
worker_model
rejected_model
archived_model
```

No model should be promoted without a report in `studbook/`.

---

## Dataset rules

```text
datasets/raw/      = raw source data and raw tasks
datasets/golden/   = selected training-approved samples
datasets/rejected/ = rejected samples for analysis
datasets/eval/     = evaluation-only data
```

Important:

```text
Do not train on rejected data.
Do not train on eval data.
Do not add unvalidated generations to golden datasets.
```

---

## Safe interruption

All long operations must be restartable.

Required mechanisms:

```text
run_id
task statuses
partial result saving
checkpoints
logs
resume support
```

The project must allow manual stop and later continuation.

---

## Agent rules

Agents working on this project must follow these rules:

```text
1. Do not mix code, data, model artifacts, configs, and logs.
2. Do not use heavy models without explicit justification.
3. Do not delete model history or lineage.
4. Do not overwrite generation reports.
5. Do not train on rejected or evaluation data.
6. Do not promote models without Bereiter evaluation.
7. Keep all model decisions recorded in studbook/.
8. Prefer small, fast, specialized models.
```

---

## Final project direction

Selection Farm is a controlled breeding and testing system for small models.

LLMs are adapted from ready open-source bases.  
Classical ML models can be trained from scratch on project data.  
Hybrid models combine ML decision speed with LLM explanation and formatting.

The final goal is to produce reliable worker models and preserve useful breeding models for future generations.
