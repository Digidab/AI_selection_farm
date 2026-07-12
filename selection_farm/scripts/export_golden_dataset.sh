#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd -- "${PROJECT_ROOT}/.." && pwd)"
PYTHON="${WORKSPACE_ROOT}/venv_ai_selection_farm/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
    echo "Project Python is unavailable: ${PYTHON}" >&2
    exit 1
fi

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    "${PYTHON}" -c '
import sys
from pathlib import Path

from services.selector.app.core.export import (
    AtomicExportWriter,
    BranchExportRequest,
    ExportCoordinator,
    PostgresExportSource,
    connect_export_database,
)
from services.selector.app.llm.config import load_llm_config
from services.selector.app.llm.exporter import LLMExportSerializer
from services.selector.app.ml.config import load_ml_config
from services.selector.app.ml.exporter import MLExportSerializer

project_root = Path(sys.argv[1])
llm = load_llm_config()
ml = load_ml_config()
if llm.common != ml.common or not llm.common.export.atomic_replace:
    raise RuntimeError("Branch configs must share atomic common export settings")
connection = connect_export_database(llm.common)
try:
    summaries = ExportCoordinator(
        PostgresExportSource(connection),
        AtomicExportWriter(),
    ).export_all(
        (
            BranchExportRequest(
                dataset_id=llm.llm.dataset_id,
                serializer=LLMExportSerializer(),
                accepted_path=project_root / "datasets/golden/golden_llm_v001.jsonl",
                rejected_path=project_root / "datasets/rejected/rejected_llm_v001.jsonl",
            ),
            BranchExportRequest(
                dataset_id=ml.ml.dataset_id,
                serializer=MLExportSerializer(),
                accepted_path=project_root / "datasets/golden/golden_ml_v001.jsonl",
                rejected_path=project_root / "datasets/rejected/rejected_ml_v001.jsonl",
            ),
        )
    )
finally:
    connection.close()

for summary in summaries:
    print(
        f"{summary.branch_id}: accepted={summary.accepted_count} "
        f"rejected={summary.rejected_count}"
    )
' "${PROJECT_ROOT}"
