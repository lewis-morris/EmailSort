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
Usage: scripts/run_email.sh [options]

Runs daily triage. By default all actions are enabled (draft replies, create tasks,
send summary email, log to file). Flags can disable each action.

Options:
  -c, --config PATH         Path to config TOML (default: REPO/config/config.toml)
  -a, --account EMAIL       Target account (may be repeated for multiple)
      --draft-replies       Enable drafting replies (default)
      --no-draft-replies    Disable drafting replies
      --create-tasks        Enable task creation (default)
      --no-create-tasks     Disable task creation
      --summary-email       Enable summary email sending (default)
      --no-summary-email    Disable summary email
      --log-to-file         Enable per-run log file (default)
      --no-log-to-file      Disable per-run log file
  -v, --verbose             Increase logging verbosity (repeatable)
  -h, --help                Show this help and exit
EOF
}

CONFIG="${DEFAULT_CONFIG}"
VERBOSE=0
ACCOUNTS=()
DRAFT_REPLIES=1
CREATE_TASKS=1
SUMMARY_EMAIL=1
LOG_TO_FILE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--config) CONFIG="$2"; shift 2 ;;
    -a|--account) ACCOUNTS+=("$2"); shift 2 ;;
    --draft-replies) DRAFT_REPLIES=1; shift ;;
    --no-draft-replies) DRAFT_REPLIES=0; shift ;;
    --create-tasks) CREATE_TASKS=1; shift ;;
    --no-create-tasks) CREATE_TASKS=0; shift ;;
    --summary-email) SUMMARY_EMAIL=1; shift ;;
    --no-summary-email) SUMMARY_EMAIL=0; shift ;;
    --log-to-file) LOG_TO_FILE=1; shift ;;
    --no-log-to-file) LOG_TO_FILE=0; shift ;;
    -v|--verbose) VERBOSE=$((VERBOSE+1)); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run_email_${STAMP}.log"
RUN_ID="${RUN_ID:-run-${STAMP}}"

CMD_ARGS=( -m email_categorise run --config "${CONFIG}" --run-id "${RUN_ID}" )
for acc in "${ACCOUNTS[@]}"; do
  CMD_ARGS+=( -a "${acc}" )
done

# Feature toggles map to CLI overrides (added in email_categorise.cli)
[[ ${DRAFT_REPLIES} -eq 1 ]] && CMD_ARGS+=( --draft-replies ) || CMD_ARGS+=( --no-draft-replies )
[[ ${CREATE_TASKS} -eq 1 ]] && CMD_ARGS+=( --create-tasks ) || CMD_ARGS+=( --no-create-tasks )
[[ ${SUMMARY_EMAIL} -eq 1 ]] && CMD_ARGS+=( --summary-email ) || CMD_ARGS+=( --no-summary-email )
[[ ${LOG_TO_FILE} -eq 1 ]] && CMD_ARGS+=( --log-to-file ) || CMD_ARGS+=( --no-log-to-file )

for ((i=0; i<VERBOSE; i++)); do
  CMD_ARGS+=( -v )
done

set +e
"${PYTHON}" "${CMD_ARGS[@]}" 2>&1 | tee "${LOG_FILE}"
EXIT_CODE=${PIPESTATUS[0]}
set -e

exit "${EXIT_CODE}"
