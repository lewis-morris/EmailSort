#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOOLS_ENV_ROOT="${HOME}/.codex-tools/environments"
PYTHON="${TOOLS_ENV_ROOT}/python-tools/bin/python"
if [[ ! -x "$PYTHON" && -x "${HOME}/.codex-tools/python-tools/bin/python" ]]; then
  PYTHON="${HOME}/.codex-tools/python-tools/bin/python"
fi
DEFAULT_CONFIG="${REPO_ROOT}/config/config.toml"
LOG_DIR="${REPO_ROOT}/output"
mkdir -p "${LOG_DIR}"

usage() {
  cat <<'EOF'
Usage: scripts/init_email.sh [options]

Runs initial mailbox setup: connectivity checks, sample polling, and tone/profile learning.

Options:
  -c, --config PATH     Path to config TOML (default: REPO/config/config.toml)
  -a, --account EMAIL   Target account (may be repeated for multiple)
  -v, --verbose         Increase logging verbosity (repeatable)
  -h, --help            Show this help and exit
EOF
}

CONFIG="${DEFAULT_CONFIG}"
VERBOSE=0
ACCOUNTS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--config) CONFIG="$2"; shift 2 ;;
    -a|--account) ACCOUNTS+=("$2"); shift 2 ;;
    -v|--verbose) VERBOSE=$((VERBOSE+1)); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/init_email_${STAMP}.log"

CMD_ARGS=( -m email_categorise init --config "${CONFIG}" )
for acc in "${ACCOUNTS[@]}"; do
  CMD_ARGS+=( -a "${acc}" )
done
for ((i=0; i<VERBOSE; i++)); do
  CMD_ARGS+=( -v )
done

set +e
"${PYTHON}" "${CMD_ARGS[@]}" 2>&1 | tee "${LOG_FILE}"
EXIT_CODE=${PIPESTATUS[0]}
set -e

exit "${EXIT_CODE}"
