# Selector Core

## Mission

`core/` owns branch-neutral orchestration and infrastructure contracts shared by Selector branches.
It must never contain LLM or ML business rules.

## Files

- `config.py` — common configuration boundary.
- `interfaces.py` — neutral branch protocols.
- `schemas.py` — neutral runtime records.
- `ids.py` — production and injectable ID adapters.
- `db.py` — PostgreSQL repository boundary.
- `pipeline.py` — lifecycle and resume orchestration boundary.
- `export.py` — DB-first export coordination boundary.
- `logging_config.py` — correlation logging boundary.

## Ownership

Allowed dependency direction is `llm -> core <- ml`. Core must not import either branch.

Task 3 implements strict common YAML loading, project-root path resolution, neutral lifecycle and
decision records, the `SelectorBranch` protocol, and correlation-aware logging. Task 6 adds the
injectable/production ID boundary, typed PostgreSQL repository, legal lifecycle transitions, atomic
counters, advisory-lock idempotence, and evidence-based resume foundations.

Task 11 implements the neutral joined DB export row, deterministic sample ordering, canonical JSONL
encoding, and rollback-capable atomic publication across all requested branch targets. Core accepts
injected serializers and never imports a branch.

Task 12 implements the injected `SelectorPipeline`: exact model-type preflight before run creation,
idempotent source import, durable execution/validation/finalization checkpoints, resume from stored
evidence, and atomic terminal status/counter updates. Branch work runs outside repository
transactions, and any partial failure marks the run failed and raises an explicit pipeline error.

Task 13 live integration verifies exact model-type preflight, two isolated completed runs, atomic
`1/1` processed/accepted counters, DB-first export, fake-provider ID isolation, and zero temporary
rows after cleanup. Deterministic tests separately resume both branch identities without repeating
execution and expose partial failure as a failed run.
