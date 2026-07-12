# Raw LLM Tasks

## Mission

This directory owns immutable source tasks for the isolated LLM Selector branch.

## Files

- `tasks_v001.jsonl` — deterministic v001 prompt/message fixtures with expected JSON Schemas.

## Ownership

Each `task_id` is a stable raw-source identity, not a production `farm.tasks.task_id`; Core assigns
runtime IDs through the approved ID provider in Task 6. Do not edit a published task file in place.
Create a new version instead. ML tasks and generated exports must never be stored here.
