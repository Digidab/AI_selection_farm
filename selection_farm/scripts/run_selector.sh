#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" != "--branch" || -z "${2:-}" ]]; then
  echo "Usage: ${BASH_SOURCE[0]##*/} --branch {llm|ml} [branch options...]" >&2
  exit 2
fi

branch="$2"
shift 2

case "$branch" in
  llm)
    exec "$SCRIPT_DIR/run_selector_llm.sh" "$@"
    ;;
  ml)
    exec "$SCRIPT_DIR/run_selector_ml.sh" "$@"
    ;;
  *)
    echo "Unsupported Selector branch: $branch" >&2
    exit 2
    ;;
esac
