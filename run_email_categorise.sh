#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${HOME}/.codex-tools/python-tools/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Expected python-tools interpreter at $PYTHON" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%d-%H%M%S)"
CMD="${1:-run}"
LOG_DIR="${SCRIPT_DIR}/output"
mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/email_categorise_${CMD}_${STAMP}.log"

# Run and tee log
set +e
"$PYTHON" -m email_categorise "$@" 2>&1 | tee "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
set -e

exit $EXIT_CODE
