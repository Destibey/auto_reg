#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${AUTOREG_LAUNCH_LABEL:-com.autoreg.backend}"
PYTHON_BIN="${AUTOREG_PYTHON:-$ROOT_DIR/.venv/bin/python}"
HOST_VALUE="${AUTOREG_HOST:-${HOST:-0.0.0.0}}"
PORT_VALUE="${AUTOREG_PORT:-${PORT:-8000}}"
SOLVER_VALUE="${APP_ENABLE_SOLVER:-1}"
LOG_FILE="${AUTOREG_LOG_FILE:-$ROOT_DIR/backend.log}"
PID_FILE="${AUTOREG_PID_FILE:-$ROOT_DIR/backend.pid}"

quote() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

service_output() {
  launchctl list "$LABEL" 2>/dev/null || true
}

service_pid() {
  service_output | awk -F'= ' '/"PID"/ {gsub(/[;[:space:]]/, "", $2); print $2; exit}'
}

port_pid() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$PORT_VALUE" -sTCP:LISTEN 2>/dev/null | head -n 1
  fi
}

is_running() {
  local pid
  pid="$(service_pid)"
  if [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1; then
    return 0
  fi
  pid="$(port_pid)"
  [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1
}

wait_for_stopped() {
  local deadline pid
  deadline=$((SECONDS + 8))
  while (( SECONDS < deadline )); do
    pid="$(service_pid)"
    if [[ -z "$pid" ]]; then
      pid="$(port_pid)"
    fi
    if [[ -z "$pid" ]] || ! ps -p "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

wait_for_started() {
  local deadline
  deadline=$((SECONDS + 12))
  while (( SECONDS < deadline )); do
    if is_running; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

start_service() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python not found or not executable: $PYTHON_BIN" >&2
    exit 1
  fi

  if is_running; then
    echo "AutoReg is already running."
    status_service
    return
  fi

  if [[ -n "$(service_output)" ]]; then
    launchctl remove "$LABEL" >/dev/null 2>&1 || true
  fi

  local command
  command="exec >> $(quote "$LOG_FILE") 2>&1; "
  command+="cd $(quote "$ROOT_DIR"); "
  command+="echo \\\$\\\$ > $(quote "$PID_FILE"); "
  command+="export APP_ENABLE_SOLVER=$(quote "$SOLVER_VALUE") HOST=$(quote "$HOST_VALUE") PORT=$(quote "$PORT_VALUE"); "
  command+="exec $(quote "$PYTHON_BIN") main.py"

  launchctl submit -l "$LABEL" -- /bin/zsh -lc "$command"
  wait_for_started || true
  status_service
}

stop_service() {
  if [[ -n "$(service_output)" ]]; then
    launchctl remove "$LABEL" >/dev/null 2>&1 || true
  fi

  local pid command
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1; then
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command" == *"main.py"* && "$command" == *"python"* ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  fi
  wait_for_stopped || true
  echo "AutoReg stopped."
}

status_service() {
  local output pid
  output="$(service_output)"
  pid="$(service_pid)"
  if [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1; then
    echo "AutoReg launchd: running (label=$LABEL pid=$pid)"
  elif [[ -n "$(port_pid)" ]]; then
    echo "AutoReg process: running without launchd label (pid=$(port_pid))"
  elif [[ -n "$output" ]]; then
    echo "AutoReg launchd: registered but not running"
    echo "$output"
  else
    echo "AutoReg launchd: not registered"
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$PORT_VALUE" -sTCP:LISTEN 2>/dev/null || true
  fi

  if command -v curl >/dev/null 2>&1; then
    if curl -fsS "http://127.0.0.1:$PORT_VALUE/" >/dev/null 2>&1; then
      echo "HTTP check: ok http://127.0.0.1:$PORT_VALUE/"
    else
      echo "HTTP check: failed http://127.0.0.1:$PORT_VALUE/"
    fi
  fi
}

restart_service() {
  stop_service
  start_service
}

logs_service() {
  tail -n "${AUTOREG_LOG_LINES:-120}" "$LOG_FILE"
}

follow_logs() {
  tail -n "${AUTOREG_LOG_LINES:-120}" -f "$LOG_FILE"
}

open_page() {
  start_service
  if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:$PORT_VALUE/"
  else
    echo "Open http://127.0.0.1:$PORT_VALUE/"
  fi
}

usage() {
  cat <<EOF
Usage: scripts/autoreg_service.sh <command>

Commands:
  start     Start AutoReg with launchctl, no extra terminal window
  stop      Stop AutoReg
  restart   Stop and start AutoReg
  status    Show launchd, port, and HTTP status
  logs      Print recent backend logs
  follow    Follow backend logs
  open      Start AutoReg and open the management page

Defaults:
  APP_ENABLE_SOLVER=$SOLVER_VALUE
  HOST=$HOST_VALUE
  PORT=$PORT_VALUE
EOF
}

case "${1:-status}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) restart_service ;;
  status) status_service ;;
  logs) logs_service ;;
  follow) follow_logs ;;
  open) open_page ;;
  -h|--help|help) usage ;;
  *)
    usage
    exit 2
    ;;
esac
