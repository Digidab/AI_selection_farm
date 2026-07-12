#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd -- "$PROJECT_ROOT/.." && pwd)"
PYTHON="$WORKSPACE_ROOT/venv_ai_selection_farm/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Project Python venv is unavailable: $PYTHON" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m services.selector.app.llm.main "$@"
