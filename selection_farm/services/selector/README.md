# Selector

Selector is the strict, DB-first quality gate for registered LLM and ML candidates.

## Package boundaries

```text
llm  ──────> core <────── ml
```

- `app/core/` owns branch-neutral lifecycle, persistence, IDs, logging, and export coordination.
- `app/llm/` owns LLM composition, structured output, embeddings, and semantic deduplication.
- `app/ml/` owns typed features, estimator inference, ML validation, and exact deduplication.

Core must not import a branch, and branches must not import one another. The architecture test
enforces these rules. Tasks 2–7 provide the scaffold, neutral Core contracts/repository/resume
foundations, strict isolated LLM/ML inputs, and the LLM component seam. The LLM reference allowlist
contains `single_turn`, `ollama`, and `text`; profile capability checks precede later run creation,
and Ollama generation/embedding calls are direct, non-streaming, timeout-bound, and bounded-retry.
Task 8 adds strict object-only JSON parsing, Draft 2020-12 schema evidence, and LLM-only
same-dataset pgvector semantic deduplication; invalid output stops before embedding and the
duplicate threshold is inclusive. Task 9 adds the ML adapter/registry seam and the trusted-local
`sklearn_generic` producer with ordered features and conditional probabilities. Task 10 adds ML
class/range/probability/confidence validation and exact accepted-sample deduplication scoped to one
ML dataset. The obsolete flat Selector stubs were removed instead of retained as a compatibility
layer. Task 11 adds DB-first branch-owned serialization and atomic four-file accepted/rejected
publication. Task 12 assembles separate end-to-end branches behind the neutral injected Core
pipeline. It verifies the exact registry model type before run creation, checkpoints execution and
validation outside DB transactions, resumes from durable evidence, and atomically accounts for
accepted, rejected, and failed tasks. Host entrypoints require an explicit `llm` or `ml` branch.

Task 13 verifies the assembled boundary against live PostgreSQL with temporary model rows: mocked
LLM generation plus 768D evidence and tmp joblib/sklearn ML inference each complete one isolated
accepted run, produce exact counters, and publish distinct byte-stable exports. Wrong model type
creates no run, ML creates no embedding row, and FK-safe cleanup leaves no `_tz08_` evidence.
Installed Ollama `qwen3:0.6b` passes structured generation; live embedding remains explicitly
inconclusive because `nomic-embed-text` is not installed and no pull/fallback is permitted.
