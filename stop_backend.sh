#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
SOLVER_PORT="${SOLVER_PORT:-8889}"
PID_FILE="${PID_FILE:-$ROOT/backend.pid}"
EXTRA_PORTS_RAW="${EXTRA_PORTS:-}"

kill_pid() {
  local pid="$1"
  if [[ -z "$pid" ]] || ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  echo "[INFO] 停止进程 PID=$pid"
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..15}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "[WARN] PID=$pid 未及时退出，执行强制停止"
  kill -9 "$pid" >/dev/null 2>&1 || true
}

pids_by_port() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return 0
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' | sed '/^$/d' || true
    return 0
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v p=":$port" '
      index($4, p) > 0 {
        while (match($0, /pid=[0-9]+/)) {
          print substr($0, RSTART + 4, RLENGTH - 4)
          $0 = substr($0, RSTART + RLENGTH)
        }
      }
    ' | sort -u || true
    return 0
  fi
}

declare -A seen=()
collect_and_kill() {
  local pid="$1"
  [[ -n "$pid" ]] || return 0
  if [[ -z "${seen[$pid]:-}" ]]; then
    seen[$pid]=1
    kill_pid "$pid"
  fi
}

if [[ -f "$PID_FILE" ]]; then
  collect_and_kill "$(tr -d '[:space:]' < "$PID_FILE")"
  rm -f "$PID_FILE"
fi

ports=("$BACKEND_PORT" "$SOLVER_PORT")
if [[ -n "$EXTRA_PORTS_RAW" ]]; then
  IFS=',' read -r -a extra_ports <<<"$EXTRA_PORTS_RAW"
  for port in "${extra_ports[@]}"; do
    port="${port// /}"
    [[ -n "$port" ]] && ports+=("$port")
  done
fi

for port in "${ports[@]}"; do
  while IFS= read -r pid; do
    collect_and_kill "$pid"
  done < <(pids_by_port "$port")
done

echo "[OK] 停止完成"
