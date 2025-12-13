#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_ENV_ROOT="${HOME}/.codex-tools/environments"
PYTHON="${TOOLS_ENV_ROOT}/python-tools/bin/python"
if [[ ! -x "$PYTHON" && -x "${HOME}/.codex-tools/python-tools/bin/python" ]]; then
  PYTHON="${HOME}/.codex-tools/python-tools/bin/python"
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Expected python-tools interpreter at $PYTHON" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%d-%H%M%S)"
CMD="${1:-run}"
shift || true

# Prefer new scripts entrypoints for init/run; fall back to python -m for other commands.
RUN_SCRIPT="${SCRIPT_DIR}/scripts/run_email.sh"
INIT_SCRIPT="${SCRIPT_DIR}/scripts/init_email.sh"

if [[ "$CMD" == "run" && -x "$RUN_SCRIPT" ]]; then
  exec "$RUN_SCRIPT" "$@"
elif [[ "$CMD" == "init" && -x "$INIT_SCRIPT" ]]; then
  exec "$INIT_SCRIPT" "$@"
else
  LOG_DIR="${SCRIPT_DIR}/output"
  mkdir -p "$LOG_DIR"
  LOG_FILE="${LOG_DIR}/email_categorise_${CMD}_${STAMP}.log"
  set +e
  "$PYTHON" -m email_categorise "$CMD" "$@" 2>&1 | tee "$LOG_FILE"
  EXIT_CODE=${PIPESTATUS[0]}
  set -e
  exit $EXIT_CODE
fi
