# Selector ML Branch

## Mission

`ml/` owns typed features, explicit model-family pipeline delegation, estimator decisions, ML-only
validation, exact canonical-input duplicate policy, serialization, and the ML entrypoint.

## Files and directories

- `config.py`, `schemas.py` — ML-only configuration and records.
- `pipelines/` — allowlisted model-family adapter seam and v001 scikit-learn boundary.
- `producer.py` — registry-based adapter delegation boundary.
- `validators.py`, `deduplicator.py` — ML decision and exact duplicate boundaries.
- `exporter.py`, `main.py` — ML serialization and entrypoint boundaries.

## Ownership

This branch may import `core` but must not import `llm`. It must not call Ollama or use embeddings.

Task 5 implements strict ML configuration, typed ordered feature records, classification/regression
rules, optional confidence rules, safe project paths, canonical JSON identity, immutable JSONL
loading, and the `sklearn_generic` pipeline descriptor. Task 9 implements the adapter protocol,
explicit registry, trusted local joblib loading, stable ordered feature preparation, typed
classification/regression prediction, and conditional probability calls.

Task 10 implements classification/regression validation, probability/confidence rules, and exact
canonical-input duplicate detection. Validation always precedes duplicate lookup. Identity is the
feature object after strict config-owned type validation: key order is ignored, integer/float fields
are not interchangeable, and accepted comparisons are limited to the same ML dataset.

Task 11 implements the ML serializer shape: ordered feature payload, prediction/probabilities,
mandatory pipeline/artifact identity, validation evidence, disposition, model identity, and
provenance. Task 12 assembles the explicit ML adapter registry, immutable typed tasks, exact
accepted-input lookup, branch evaluation, and the neutral Core pipeline in `main.py`. It is invoked
only through the dedicated ML entrypoint or explicit dispatcher branch and never touches the LLM
runtime or embedding storage.

Task 13 runs the assembled ML branch against live PostgreSQL with a temporary registry row and a
pytest-owned joblib/scikit-learn artifact. Explicit `sklearn_generic` resolution, prediction,
validation, exact dedup lookup, counters, DB-first export, and cleanup pass; the resulting ML run
creates no embedding evidence and cannot enter the LLM dataset/export.
