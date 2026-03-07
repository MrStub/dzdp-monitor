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
  help-zh)
    cat <<'EOF'
dzdp-monitor-openclaw 中文命令清单

一、监控运行
  run_monitor.sh once [--config <config_path>]
  run_monitor.sh start [--config <config_path>]
  run_monitor.sh test-email [--config <config_path>]

二、套餐管理
  run_monitor.sh targets [--config <config_path>] list [--json]
  run_monitor.sh targets [--config <config_path>] add --name "<套餐名>" --url "<链接>" [--json]
  run_monitor.sh targets [--config <config_path>] get --index <序号> [--json]
  run_monitor.sh targets [--config <config_path>] get --name "<套餐名>" [--json]
  run_monitor.sh targets [--config <config_path>] get --url "<链接>" [--json]
  run_monitor.sh targets [--config <config_path>] get --activity-id <activityid> [--json]
  run_monitor.sh targets [--config <config_path>] update --index <序号> --set-name "<新套餐名>" [--json]
  run_monitor.sh targets [--config <config_path>] update --index <序号> --set-url "<新链接>" [--json]
  run_monitor.sh targets [--config <config_path>] remove --index <序号> [--json]
  run_monitor.sh targets [--config <config_path>] remove --name "<套餐名>" [--json]
  run_monitor.sh targets [--config <config_path>] remove --url "<链接>" [--json]
  run_monitor.sh targets [--config <config_path>] remove --activity-id <activityid> [--json]

三、轮询时间
  run_monitor.sh poll [--config <config_path>] get [--json]
  run_monitor.sh poll [--config <config_path>] set --seconds <秒数> [--json]

常用中文口令：
  查看监控列表
  添加监控：套餐名，链接
  删除监控：序号
  删除监控：套餐名
  查看轮询时间
  修改轮询时间：30秒
  单次检查库存

说明：
  - 链接会自动去掉 shareid
  - 套餐列表和轮询时间修改会热更新到运行中的监控进程
  - 最小轮询时间是 5 秒
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
    echo "  run_monitor.sh help-zh" >&2
    echo "  run_monitor.sh {once|start|test-email} [--config <config_path>]" >&2
    echo "  run_monitor.sh targets [--config <config_path>] {list|get|add|update|remove} ..." >&2
    echo "  run_monitor.sh poll [--config <config_path>] {get|set --seconds <n>}" >&2
    exit 1
    ;;
esac
