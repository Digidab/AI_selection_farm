# Selector ML Unit Tests

This directory verifies strict ML-only configuration, ordered typed features, explicit
`sklearn_generic` selection, prediction rules, optional confidence, finite numbers, canonical JSON
identity, and immutable JSONL loading.

Task 9 coverage uses deterministic scikit-learn classification/regression artifacts written only
under pytest `tmp_path`. It verifies stable feature order, conditional probability calls, typed
evidence, corrupt/missing/API failures, unknown pipeline rejection, and test-only adapter
substitution without producer changes.

Task 10 coverage verifies class/range/probability/confidence boundaries, auditable rejection
evidence, validation-before-lookup ordering, canonical key-order independence, strict numeric
feature types, and exact duplicate decisions.

Tests must not import the LLM branch, access PostgreSQL/network services, or commit binary artifacts.
