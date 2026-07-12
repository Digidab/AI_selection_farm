# Selector Unit Tests

Unit tests are organized by the same isolated package boundaries as Selector runtime code.

- `core/` — branch-neutral contracts and utilities.
- `llm/` — strict LLM config, task schema, and immutable input tests.
- `ml/` — typed feature, prediction config, canonical identity, and immutable input tests.

Tests must not share branch-specific fixtures across `llm` and `ml`.
