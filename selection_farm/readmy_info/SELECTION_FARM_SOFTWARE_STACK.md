# Selection Farm — Software Stack Guide

## 1. Purpose

This document lists the software, utilities, Python libraries, Docker services, VS Code extensions, and optional tools required for the **Selection Farm** project.

Target environment:

```text
Windows 11 Pro host
VMware Workstation Pro
Debian 13 VM
CPU-first / CPU-only AI execution
VS Code inside Debian 13
Docker inside Debian 13
Small and resource-efficient models only
```

Main project rule:

```text
Models must be small, fast, specialized, and suitable for resource-limited pipelines.
```

---

## 2. Installation phases

Use phased installation. Do not install everything at once.

```text
Phase 1 — Core OS + development tools
Phase 2 — VS Code + extensions
Phase 3 — Docker + base containers
Phase 4 — Python service dependencies
Phase 5 — ML training stack
Phase 6 — LLM inference stack
Phase 7 — LLM fine-tuning stack later
Phase 8 — MLOps and dataset versioning later
```

---

# Phase 1 — Debian system utilities

## Required APT packages

```bash
sudo apt update
sudo apt install -y \
  git \
  curl \
  wget \
  make \
  tree \
  htop \
  btop \
  tmux \
  jq \
  yq \
  nano \
  vim \
  unzip \
  ca-certificates \
  gnupg \
  lsb-release \
  build-essential \
  pkg-config \
  cmake \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev
```

## Purpose

| Package | Purpose |
|---|---|
| `git` | Source control |
| `curl`, `wget` | Download scripts and packages |
| `make` | Short project commands |
| `tree` | Directory tree inspection |
| `htop`, `btop` | CPU/RAM monitoring |
| `tmux` | Long sessions without terminal loss |
| `jq` | JSON processing |
| `yq` | YAML processing |
| `nano`, `vim` | Terminal editing |
| `build-essential` | Native compilation support |
| `pkg-config`, `cmake` | Build helpers for Python packages |
| `python3-venv` | Python virtual environments |
| `python3-dev` | Python headers for compiled packages |

---

# Phase 2 — VS Code inside Debian 13

## Required software

Install **Visual Studio Code** inside Debian 13 VM.

VS Code is the main IDE for:

```text
Python development
Docker Compose editing
YAML config editing
SQL editing
debugging selector / bereiter / trainer
project refactoring
```

## Required VS Code extensions

```text
Python                                   [installed]
Pylance                                  [installed]
Ruff                                     [installed]
Black Formatter                         [installed]
Docker                                   [not needed — using Portainer instead]
YAML                                     [installed]
SQLTools
SQLTools PostgreSQL/Cockroach Driver
Makefile Tools                          [installed]
GitLens
Markdown All in One
```

## Optional VS Code extensions

```text
Even Better TOML
EditorConfig for VS Code
REST Client
Git Graph
Mermaid Markdown Syntax Highlighting
```

---

# Phase 3 — Docker infrastructure

## Required Docker packages

```text
docker-ce
docker-ce-cli
containerd.io
docker-buildx-plugin
docker-compose-plugin
```

Docker files are stored under:

```text
selection_farm/docker/
```

## Docker services for the farm

```text
ollama
postgres + pgvector
selector
bereiter
trainer
```

Initial Docker layout:

```text
docker/
├── docker-compose.yml
├── .env.example
├── postgres/
│   └── init.sql
├── selector/
│   └── Dockerfile
├── bereiter/
│   └── Dockerfile
└── trainer/
    └── Dockerfile
```

## Docker command pattern

From project root:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d
docker compose -f docker/docker-compose.yml --env-file docker/.env down
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f
```

Prefer wrapping these commands in `Makefile`.

---

# Phase 4 — Docker containers

## Ollama

Role:

```text
local LLM inference runtime
small LLM execution
embedding model execution
CPU-only mode inside VMware
```

Recommended first models:

```bash
ollama pull qwen3:0.6b
ollama pull qwen3:1.7b
ollama pull llama3.2:1b
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

Resource rule:

```text
0.6B–1B     = fast experiments
1.5B–1.7B  = main working range
3B         = upper normal range
4B         = occasional judge only
7B+        = rare benchmark only
```

## PostgreSQL + pgvector

Role:

```text
task status tracking
generation history
model registry backend
embedding storage
semantic deduplication
run metadata
```

Recommended image:

```text
pgvector/pgvector:pg16-trixie
```

Alternative if needed:

```text
pgvector/pgvector:pg16
```

## Selector container

Role:

```text
strict validation
candidate rejection
golden dataset writing
embedding deduplication
PostgreSQL run logging
```

## Bereiter container

Role:

```text
model trials
accuracy measurement
latency measurement
RAM measurement
worker/breeding/rejected recommendation
```

## Trainer container

Role:

```text
classical ML training
LoRA/QLoRA later
checkpoint management
model export
```

For the first MVP, trainer should focus on ML models first.

---

# Phase 5 — Python environment strategy

Use separate dependency files per service:

```text
services/selector/requirements.txt
services/bereiter/requirements.txt
services/trainer/requirements.txt
services/trainer/requirements-llm.txt
```

Do not put all dependencies into one global requirements file.

## Shared base dependencies

```text
pydantic
pydantic-settings
python-dotenv
orjson
loguru
rich
tenacity
```

| Package | Purpose |
|---|---|
| `pydantic` | Strict schemas |
| `pydantic-settings` | Typed settings |
| `python-dotenv` | Local env loading |
| `orjson` | Fast JSON |
| `loguru` | Logging |
| `rich` | Terminal reports |
| `tenacity` | Retry logic |

---

# Phase 6 — Selector dependencies

## `services/selector/requirements.txt`

```text
pydantic
pydantic-settings
python-dotenv
httpx
orjson
psycopg[binary]
pgvector
loguru
rich
tenacity
```

| Package | Purpose |
|---|---|
| `httpx` | HTTP calls to Ollama |
| `psycopg[binary]` | PostgreSQL client |
| `pgvector` | Vector type support |
| `orjson` | Fast JSON parsing/writing |
| `pydantic` | Validation schemas |
| `tenacity` | Retry on temporary service errors |

---

# Phase 7 — Bereiter dependencies

## `services/bereiter/requirements.txt`

```text
pydantic
pydantic-settings
python-dotenv
psutil
numpy
pandas
orjson
loguru
rich
```

| Package | Purpose |
|---|---|
| `psutil` | CPU/RAM/process monitoring |
| `numpy` | Numeric metrics |
| `pandas` | Evaluation tables |
| `rich` | Trial reports in terminal |
| `orjson` | Fast report serialization |

---

# Phase 8 — Trainer ML dependencies

## `services/trainer/requirements.txt`

Recommended ML training stack:

```text
numpy
pandas
scipy
scikit-learn
joblib
lightgbm
xgboost
catboost
imbalanced-learn
optuna
mlflow
onnx
onnxruntime
skl2onnx
pydantic
pydantic-settings
python-dotenv
orjson
loguru
rich
psutil
```

## Purpose by group

### Numeric and tabular base

```text
numpy
pandas
scipy
```

Used for arrays, tables, statistical processing, and feature engineering.

### Classical ML

```text
scikit-learn
```

Used for:

```text
classification
regression
preprocessing
pipelines
metrics
cross-validation
model selection
```

### Gradient boosting models

```text
lightgbm
xgboost
catboost
```

Used for:

```text
buy/sell/hold classifiers
scoring models
ranking models
risk models
tabular prediction
```

### Imbalanced data

```text
imbalanced-learn
```

Used when one class dominates the dataset.

Example:

```text
hold = frequent
buy/sell = rare
```

### Hyperparameter search

```text
optuna
```

Used for controlled hyperparameter optimization.

### Experiment tracking

```text
mlflow
```

Used for:

```text
experiment tracking
metrics
model registry later
model lineage integration
```

### Export and inference

```text
onnx
onnxruntime
skl2onnx
joblib
```

Used for:

```text
saving models
exporting lightweight production models
fast CPU inference
pipeline integration
```

---

# Phase 9 — LLM inference stack

## Runtime

Primary runtime:

```text
Ollama
```

Used for:

```text
Qwen small models
Llama small models
Gemma small models
Phi small models
embedding models
judge models
```

## Python client packages

For selector and helper scripts:

```text
httpx
orjson
pydantic
```

Optional later:

```text
openai
```

Only if Ollama or another local runtime is exposed through an OpenAI-compatible API.

## Embedding models

Recommended first embedding model:

```text
nomic-embed-text
```

Possible later options:

```text
Qwen3 embedding models
BGE small models
sentence-transformers models
```

---

# Phase 10 — LLM fine-tuning stack later

## Important warning

Do not install and use the full LLM fine-tuning stack during the first MVP.

Current environment is CPU-first / CPU-only inside VMware.  
LLM fine-tuning will be slow.

First MVP should focus on:

```text
Ollama inference
Selector validation
golden/rejected datasets
Bereiter evaluation
classical ML training
```

## `services/trainer/requirements-llm.txt`

Install later when needed:

```text
torch
transformers
datasets
peft
accelerate
trl
sentencepiece
protobuf
safetensors
tokenizers
```

| Package | Purpose |
|---|---|
| `torch` | Deep learning backend |
| `transformers` | Hugging Face model framework |
| `datasets` | Dataset loading/processing |
| `peft` | LoRA/QLoRA adapters |
| `accelerate` | Training/inference acceleration orchestration |
| `trl` | Preference tuning / RLHF-style workflows |
| `sentencepiece` | Tokenizer support |
| `safetensors` | Safe tensor storage |
| `tokenizers` | Fast tokenizer backend |

## LLM fine-tuning frameworks

Use later:

```text
LLaMA-Factory
Axolotl
```

### LLaMA-Factory

Role:

```text
unified fine-tuning framework
LoRA / QLoRA
DPO / PPO / reward modeling
many model families
web UI option
```

### Axolotl

Role:

```text
YAML-based fine-tuning framework
LoRA / QLoRA
engineering-style repeatable configs
```

For this project:

```text
LLaMA-Factory = easier first option
Axolotl = later engineering option
```

---

# Phase 11 — MLOps and data/version control

## Install later

```text
mlflow
dvc
```

`mlflow` may be used earlier in `trainer`, but full MLflow server/model registry can wait.

## MLflow role

```text
experiment tracking
metrics
model registry
lineage
model versions
```

## DVC role

```text
dataset versioning
model artifact versioning
experiment reproducibility
Git-like data workflow
```

For MVP, `studbook/` + PostgreSQL + JSONL is enough.  
DVC becomes important when datasets and models start growing.

---

# Phase 12 — Evaluation and testing stack

## Required testing packages

```text
pytest
pytest-cov
ruff
black
mypy
```

| Package | Purpose |
|---|---|
| `pytest` | Unit/integration tests |
| `pytest-cov` | Coverage |
| `ruff` | Fast linting |
| `black` | Code formatting |
| `mypy` | Static type checks |

## Required test areas

```text
JSON validation
schema validation
NaN / Infinity rejection
empty input handling
range validation
duplicate detection
PostgreSQL connection
pgvector deduplication
Ollama connection
resume-after-interruption logic
dataset writer
```

---

# Phase 13 — Optional observability tools later

Do not install now unless needed.

Possible future tools:

```text
Langfuse
Phoenix
Grafana
Prometheus
```

Use only after the core farm works.

---

# Phase 14 — Optional RAG / agent UI tools later

Do not install now.

Possible future tools:

```text
AnythingLLM
Dify
```

Use cases:

```text
project documentation RAG
log analysis
prompt management
workflow UI
human-readable experiment analysis
```

Do not give these tools direct write access to `datasets/golden/`.

---

# Phase 15 — Tools not recommended for the core MVP

Do not install in the main farm now:

```text
AutoAgent
LangChain Open Agent Platform
Sim
large 7B+ models
ROCm stack inside VMware
CUDA stack inside VMware
Docker Desktop
```

Reasons:

```text
too heavy
not needed for CPU-only VMware
adds complexity
may reduce reproducibility
may break resource-first rule
```

---

# Phase 16 — Proposed requirements files

## `services/selector/requirements.txt`

```text
pydantic
pydantic-settings
python-dotenv
httpx
orjson
psycopg[binary]
pgvector
loguru
rich
tenacity
```

## `services/bereiter/requirements.txt`

```text
pydantic
pydantic-settings
python-dotenv
psutil
numpy
pandas
orjson
loguru
rich
```

## `services/trainer/requirements.txt`

For MVP ML training:

```text
numpy
pandas
scipy
scikit-learn
joblib
lightgbm
xgboost
catboost
imbalanced-learn
optuna
mlflow
onnx
onnxruntime
skl2onnx
pydantic
pydantic-settings
python-dotenv
orjson
loguru
rich
psutil
```

## `services/trainer/requirements-llm.txt`

For later LLM fine-tuning:

```text
torch
transformers
datasets
peft
accelerate
trl
sentencepiece
protobuf
safetensors
tokenizers
```

Do not mix this with the MVP ML requirements unless LLM fine-tuning is actively being implemented.

---

# Phase 17 — Recommended install order

```text
1. Debian system utilities
2. VS Code
3. VS Code extensions
4. Docker Engine + Docker Compose Plugin
5. PostgreSQL + pgvector container
6. Ollama container
7. Python virtual environment
8. Selector dependencies
9. Bereiter dependencies
10. Trainer ML dependencies
11. Tests and lint tools
12. MLflow/DVC later
13. LLM fine-tuning stack later
```

---

# Phase 18 — Minimal MVP software set

For the first working version, install only this:

```text
Debian utilities:
git, curl, wget, make, tree, htop, btop, tmux, jq, yq,
build-essential, python3, python3-venv, python3-pip, python3-dev

IDE:
VS Code + Python + Pylance + Ruff + Docker + YAML + SQLTools

Docker:
Docker Engine
Docker Compose Plugin

Containers:
Ollama
PostgreSQL + pgvector

Python:
pydantic
pydantic-settings
httpx
orjson
psycopg[binary]
pgvector
loguru
rich
tenacity
pytest
ruff
black
numpy
pandas
scikit-learn
psutil
```

This is enough for:

```text
tasks.jsonl
→ Ollama
→ Python Selector
→ validation
→ golden/rejected datasets
→ PostgreSQL/pgvector records
→ Bereiter trial report
```

---

# Phase 19 — Source notes

Checked against official or primary documentation:

```text
Docker Engine Debian support:
https://docs.docker.com/engine/install/debian/

VS Code Linux installation:
https://code.visualstudio.com/docs/setup/linux

Ollama Docker CPU-only mode:
https://docs.ollama.com/docker

pgvector:
https://github.com/pgvector/pgvector
https://hub.docker.com/r/pgvector/pgvector

LLaMA-Factory:
https://github.com/hiyouga/LLaMA-Factory

Axolotl:
https://github.com/axolotl-ai-cloud/axolotl

scikit-learn:
https://scikit-learn.org/stable/user_guide.html

LightGBM:
https://lightgbm.readthedocs.io/

XGBoost:
https://xgboost.readthedocs.io/

CatBoost:
https://catboost.ai/docs/en/

Optuna:
https://optuna.readthedocs.io/

MLflow Model Registry:
https://mlflow.org/docs/latest/ml/model-registry/

DVC data/model versioning:
https://doc.dvc.org/example-scenarios/versioning-data-and-models

ONNX Runtime:
https://onnxruntime.ai/

Hugging Face Transformers:
https://huggingface.co/docs/transformers/en/installation

Hugging Face PEFT:
https://huggingface.co/docs/peft/en/index
```

---

# Final rule

Do not install tools just because they are popular.

Install only what supports the current farm stage:

```text
MVP first.
Stable core second.
ML training third.
LLM fine-tuning later.
MLOps after real generations appear.
```
