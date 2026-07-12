# Selector LLM Unit Tests

This directory verifies strict LLM-only configuration, exact v001 component identities, capability
descriptors, prompt/message records, expected JSON Schemas, and immutable JSONL loading.

Task 8 coverage also verifies strict JSON limits, canonicalization, Draft 2020-12 evidence,
cheap-check short-circuiting, inclusive semantic thresholds, fail-closed embedding errors, and the
complete registered output-contract/evaluator profile.

Unit tests use deterministic runtime and lookup fakes and must not import the ML branch or access
network/PostgreSQL.
