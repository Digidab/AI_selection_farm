# Selector LLM Branch

## Mission

`llm/` owns prompt-oriented evaluation, LLM component composition, structured output, embeddings,
semantic duplicate policy, branch serialization, and the LLM entrypoint.

## Files and directories

- `config.py`, `schemas.py` — LLM-only configuration and records.
- `interfaces.py`, `registry.py` — component protocols and allowlisted resolution.
- `pipelines/` — interaction orchestration components.
- `runtimes/` — model transport components.
- `modalities/` — declared input modality components.
- `output_contracts/` — explicit result parsing contracts.
- `evaluators/` — ordered LLM quality rules.
- `persistence.py` — idempotent LLM-owned accepted-generation embedding persistence.
- `exporter.py`, `main.py` — LLM serialization and entrypoint boundaries.

## Ownership

This branch may import `core` but must not import `ml`. It owns no shared DB lifecycle rules.

Tasks 4 and 7 implement strict configuration and task loading plus the capability-checked component
seam. The production allowlist contains `single_turn`, `ollama`, and `text`; its complete v001
profile is resolved before later orchestration may create a run. Ollama transport is direct httpx,
non-streaming, timeout-bound, and limited to two attempts for transient transport/HTTP failures.
Task 8 implements `structured_json`, `json_schema`, and `semantic_dedup` as explicit registered
components. Evaluation is ordered cheap-to-expensive, embeds only schema-valid canonical JSON, and
queries accepted samples in the same LLM dataset and embedding space.
The runtime rejects an embedding response whose model identity differs from the requested model
(allowing only the explicit `:latest` alias), and persistence records only that verified space.

Task 11 implements the LLM serializer shape: prompt/input/schema, raw and structured completion,
mandatory component profile, validation evidence, model identity, disposition, and provenance.
Task 12 assembles the resolved component profile, immutable LLM tasks, PostgreSQL accepted-embedding
lookup, branch evaluation, accepted embedding persistence, and the neutral Core pipeline in
`main.py`. It is invoked only through the dedicated LLM entrypoint or explicit dispatcher branch.

Task 13 runs this complete composition against live PostgreSQL with a temporary LLM registry row
and an injected protocol-compatible runtime. Structured validation, 768D persistence, counters,
DB-first export, wrong-type rejection, and cleanup pass. The installed live Ollama generation model
also passes its bounded structured call; the separate embedding model is unavailable, so a fully
live provider E2E is recorded as inconclusive without model pull or fallback.
