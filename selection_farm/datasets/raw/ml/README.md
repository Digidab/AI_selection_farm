# Raw ML Tasks

## Mission

This directory owns immutable typed feature tasks for the isolated ML Selector branch.

## Files

- `tasks_v001.jsonl` — deterministic v001 feature fixtures matching `ml_v001.yaml` order/types.

## Ownership

Each `task_id` is a stable raw-source identity, not a production `farm.tasks.task_id`; Core assigns
runtime IDs through the approved ID provider in Task 6. Feature objects are validated against the
configured ordered contract and canonicalized independently of JSON key order. Do not store LLM
tasks, serialized model artifacts, or generated exports here.
