# scripts

Operational helper scripts. Must be small, explicit, and safe.

Rule: any destructive script must require explicit confirmation.

`id_generator/` issues Selection Farm IDs (models, runs, tasks, generations, validations, samples, embeddings) — see [id_generator/README.md](id_generator/README.md) for the full context map, and [configs/id_mapping/README.md](../configs/id_mapping/README.md) for the ID format and rules.

`export_golden_dataset.sh` is the host-side DB-first publication entrypoint. Despite its historical
name, one invocation publishes four branch-owned files: accepted/rejected LLM and accepted/rejected
ML JSONL. It loads the two strict Selector configs, reads committed PostgreSQL samples, fully stages
all payloads, and atomically replaces the four files as one rollback-capable group. It never prints
database credentials and resolves the project venv from `BASH_SOURCE[0]`.

Selector execution has three explicit, CWD-independent host scripts:

```bash
scripts/run_selector.sh --branch llm [--config PATH] [--common-config PATH]
scripts/run_selector.sh --branch ml [--config PATH] [--common-config PATH]
scripts/run_selector_llm.sh [--config PATH] [--common-config PATH]
scripts/run_selector_ml.sh [--config PATH] [--common-config PATH]
```

The dispatcher never infers a branch. All three resolve paths from `BASH_SOURCE[0]`, use the
workspace `venv_ai_selection_farm`, and do not start Docker or hide a non-zero branch result.

Task 13 verification runs both dispatcher help paths from an unrelated CWD and shell-checks all
three scripts. Live E2E tests assemble branches directly with temporary model/artifact/provider
fixtures; production scripts are not pointed at those fixtures and never create a real experiment.
