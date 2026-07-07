# Selection Farm — Project Philosophy

## 1. Core idea

**Selection Farm** is a local model selection and training system focused on small, specialized, resource-efficient models.

The project is not designed to create large LLMs from scratch.  
It is designed to select, fine-tune, evaluate, register, and deploy lightweight models that can work inside resource-limited pipelines.

Main principle:

```text
Small. Fast. Specialized. Measurable. Safe to interrupt.
```

---

## 2. Resource-first rule

The target production pipeline has limited resources.

Therefore, every model selected, trained, or deployed by this project must follow the resource-first rule:

```text
A model must not consume excessive CPU, RAM, disk, or runtime resources.
```

Preferred model classes:

```text
0.6B–1B     = fast experiments and lightweight workers
1.5B–1.7B  = main working range
3B         = upper normal range
4B         = occasional judge or evaluator
7B+        = rare benchmark only, not main pipeline
```

Heavy models are not allowed in the main workflow without explicit technical justification.

---

## 3. Two model lines

Selection Farm has two main model development lines.

```text
LLM line:
ready open-source LLM
→ fine-tuning / LoRA / QLoRA
→ evaluation
→ worker_model or breeding_model

ML line:
own structured data
→ feature engineering
→ training from scratch
→ evaluation
→ worker_model
```

---

## 4. LLM line

For LLMs, the project does not build a foundation model from scratch.

Correct approach:

```text
Take a ready small open-source model
→ adapt it to our task
→ test it
→ register it
→ either use it in pipeline or keep it for future generations
```

Examples of possible base models:

```text
Qwen small models
Llama small models
Gemma small models
Phi small models
DeepSeek distilled small models
```

LLMs are useful for:

```text
text understanding
JSON generation
structured explanations
log analysis
prompt transformation
reasoning over messy input
formatting outputs
acting as judge models in limited scenarios
```

LLMs should not be forced to solve every numeric or tabular decision problem.

---

## 5. ML line

For small classical ML models, the project can create models from scratch.

Examples:

```text
buy / sell / hold classifier
scoring model
ranking model
anomaly detector
risk model
reward model
tabular model
```

Good candidates:

```text
Logistic Regression
RandomForest
LightGBM
XGBoost
CatBoost
IsolationForest
small neural networks
ranking models
```

ML models are preferred when input is structured and numeric:

```text
spreads
volumes
latency
risk scores
funding rates
order book imbalance
historical features
```

For this type of data, ML models are usually faster, cheaper, easier to test, and more stable than LLMs.

---

## 6. Hybrid line

Hybrid models combine ML and LLM roles.

Correct pattern:

```text
Raw data
→ Feature Builder
→ ML Worker Model
→ Validator / Selector
→ LLM Explainer or JSON Formatter
→ Pipeline output
```

Example:

```text
LightGBM decides: HOLD
LLM explains why and formats the result as strict JSON
Python Selector validates the final output
```

The LLM should not replace the ML model when the decision is numeric and structured.

---

## 7. Horse farm analogy

The project uses a horse breeding analogy as a working mental model.

```text
stable/      = model stables
studbook/    = breeding book and model registry
datasets/    = feed and training material
selector     = strict selection layer
bereiter     = model trial and preparation layer
trainer      = training and fine-tuning layer
worker_model = model admitted into production work
breeding_model = model admitted into future generations
```

LLM analogy:

```text
Ready open-source LLM = bought young animal from a known breed
LoRA/QLoRA fine-tuning = training and feeding under our program
Evaluation = trials
Worker model = trained work animal
Breeding model = selected breeding line
```

ML analogy:

```text
Classical ML model = small working breed we can raise from our own data
Feature engineering = controlled feeding and training plan
Evaluation = performance trial
Production admission = work approval
```

---

## 8. Model statuses

Every model must have one clear lifecycle status.

```text
raw_candidate       = downloaded or created but not tested
trained_candidate   = trained but not fully evaluated
tested_candidate    = evaluated but not yet approved
breeding_model      = approved for future generations
worker_model        = approved for production pipeline
rejected_model      = rejected due to failure or poor metrics
archived_model      = stored for history but inactive
```

No model should enter `worker_model` or `breeding_model` status without a recorded decision.

---

## 9. Mandatory model passport

Every model must have a passport.

Minimum fields:

```text
model_id
model_type
base_model
generation
parent_model_id
dataset_id
training_config_id
selector_version
bereiter_report_id
eval_score
latency
memory_usage
status
decision_reason
allowed_for_pipeline
allowed_for_breeding
```

The model passport belongs in:

```text
studbook/model_registry/
```

---

## 10. Golden dataset rule

Only selected and validated samples may enter the golden dataset.

Correct flow:

```text
raw generation
→ validation
→ rejection or acceptance
→ deduplication
→ golden dataset
```

Forbidden flow:

```text
raw generation
→ direct training
```

Training on unvalidated model-generated data is not allowed.

---

## 11. Evaluation rule

Evaluation data must stay separate from training data.

```text
datasets/golden/ = training-approved data
datasets/eval/   = evaluation-only data
datasets/rejected/ = analysis-only data
```

Do not train on `datasets/eval/`.

---

## 12. Safe interruption rule

The farm must support interruption and resume.

Long-running processes must write state regularly:

```text
run_id
task status
partial outputs
checkpoints
logs
metrics
```

A session may be stopped manually at any time.  
After restart, the system should continue from the last safe state.

---

## 13. Main architectural roles

```text
Python Selector
- validates generations
- rejects bad outputs
- writes golden/rejected datasets
- checks schema, ranges, JSON, duplicates

Bereiter
- runs practical trials
- measures speed, accuracy, stability, RAM usage
- recommends worker/breeding/rejected status

Trainer
- trains LoRA/QLoRA adapters
- trains classical ML models
- saves checkpoints
- exports models

Studbook
- stores model registry
- stores lineage
- stores generation decisions
- stores worker admissions and rejection reports

Stable
- stores model artifacts, adapters, reports, model cards
```

---

## 14. Final principle

Selection Farm is not a random collection of models.

It is a controlled system for producing small, specialized, resource-efficient models.

The goal is to create reliable worker models for real pipelines and preserve strong breeding models for future generations.
