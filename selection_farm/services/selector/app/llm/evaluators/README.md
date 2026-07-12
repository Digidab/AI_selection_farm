# LLM Evaluators

## Mission

Produce explicit evidence for ordered LLM quality rules.

## Files

- `json_schema.py` — JSON Schema evaluator boundary.
- `semantic_dedup.py` — pgvector semantic duplicate evaluator boundary.

Evaluator policy belongs to the LLM branch, never Core or ML. `LLMCandidateEvaluator` runs the
declared contract, Draft 2020-12 schema validation, and semantic deduplication in that order.
Semantic lookup compares only accepted samples with the same LLM dataset and embedding model;
`cosine_distance <= max_cosine_distance` is a duplicate. Missing or invalid embedding evidence
fails closed, and network inference finishes before the bounded database lookup transaction.
