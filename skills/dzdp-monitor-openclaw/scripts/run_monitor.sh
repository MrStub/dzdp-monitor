#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-once}"
if [[ $# -gt 0 ]]; then
  shift
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONFIG_PATH="${ROOT_DIR}/config.json"
MONITOR_PY="${ROOT_DIR}/monitor.py"
MANAGE_PY="${SCRIPT_DIR}/manage_targets.py"
POLL_PY="${SCRIPT_DIR}/manage_poll.py"

# Preferred config override: --config /path/to/config.json
if [[ "${1:-}" == "--config" && -n "${2:-}" ]]; then
  CONFIG_PATH="$2"
  shift 2
fi

# Backward compatibility:
# run_monitor.sh once /path/to/config.json
if [[ "${ACTION}" != "targets" && -n "${1:-}" && -f "${1:-}" ]]; then
  CONFIG_PATH="$1"
  shift
fi

if [[ ! -f "${MONITOR_PY}" ]]; then
  echo "monitor.py not found: ${MONITOR_PY}" >&2
  exit 2
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "config not found: ${CONFIG_PATH}" >&2
  exit 2
fi

case "${ACTION}" in
  help)
    cat <<'EOF'
dzdp-monitor-openclaw commands

Monitor:
  run_monitor.sh once [--config <config_path>]
  run_monitor.sh start [--config <config_path>]
  run_monitor.sh test-email [--config <config_path>]

Targets:
  run_monitor.sh targets [--config <config_path>] list [--json]
  run_monitor.sh targets [--config <config_path>] add --name "<name>" --url "<url>" [--json]
  run_monitor.sh targets [--config <config_path>] get --index <n> [--json]
  run_monitor.sh targets [--config <config_path>] get --name "<name>" [--json]
  run_monitor.sh targets [--config <config_path>] get --url "<url>" [--json]
  run_monitor.sh targets [--config <config_path>] get --activity-id <id> [--json]
  run_monitor.sh targets [--config <config_path>] update --index <n> --set-name "<new_name>" [--json]
  run_monitor.sh targets [--config <config_path>] update --index <n> --set-url "<new_url>" [--json]
  run_monitor.sh targets [--config <config_path>] remove --index <n> [--json]
  run_monitor.sh targets [--config <config_path>] remove --name "<name>" [--json]
  run_monitor.sh targets [--config <config_path>] remove --url "<url>" [--json]
  run_monitor.sh targets [--config <config_path>] remove --activity-id <id> [--json]

Poll:
  run_monitor.sh poll [--config <config_path>] get [--json]
  run_monitor.sh poll [--config <config_path>] set --seconds <n> [--json]

Notes:
  - target URLs are normalized by removing shareid
  - target CRUD and poll changes hot reload into the running monitor
  - minimum poll interval is 5 seconds
EOF
    ;;
  once)
    exec python3 "${MONITOR_PY}" --config "${CONFIG_PATH}" --once
    ;;
  start)
    exec python3 "${MONITOR_PY}" --config "${CONFIG_PATH}"
    ;;
  test-email)
    exec python3 "${MONITOR_PY}" --config "${CONFIG_PATH}" --test-email
    ;;
  targets)
    if [[ ! -f "${MANAGE_PY}" ]]; then
      echo "manage_targets.py not found: ${MANAGE_PY}" >&2
      exit 2
    fi
    exec python3 "${MANAGE_PY}" --config "${CONFIG_PATH}" "$@"
    ;;
  poll)
    if [[ ! -f "${POLL_PY}" ]]; then
      echo "manage_poll.py not found: ${POLL_PY}" >&2
      exit 2
    fi
    exec python3 "${POLL_PY}" --config "${CONFIG_PATH}" "$@"
    ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    echo "Usage:" >&2
    echo "  run_monitor.sh help" >&2
    echo "  run_monitor.sh {once|start|test-email} [--config <config_path>]" >&2
    echo "  run_monitor.sh targets [--config <config_path>] {list|get|add|update|remove} ..." >&2
    echo "  run_monitor.sh poll [--config <config_path>] {get|set --seconds <n>}" >&2
    exit 1
    ;;
esac
