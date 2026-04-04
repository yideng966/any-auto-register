#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="${APP_CONDA_ENV:-any-auto-register}"
BIND_HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_FILE="${LOG_FILE:-$ROOT/backend.log}"
PID_FILE="${PID_FILE:-$ROOT/backend.pid}"
RESTART_EXISTING="${RESTART_EXISTING:-1}"
START_TIMEOUT="${START_TIMEOUT:-60}"
APP_RELOAD="${APP_RELOAD:-0}"
LOG_OFFSET=0

resolve_python() {
  local python_exe=""

  if [[ -n "${APP_PYTHON:-}" && -x "${APP_PYTHON}" ]]; then
    echo "${APP_PYTHON}"
    return 0
  fi

  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
    return 0
  fi

  if command -v conda >/dev/null 2>&1; then
    python_exe="$(conda run --no-capture-output -n "$ENV_NAME" python -c 'import sys; print(sys.executable)' 2>/dev/null | tail -n 1 | tr -d '\r')"
    if [[ -n "$python_exe" && -x "$python_exe" ]]; then
      echo "$python_exe"
      return 0
    fi
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  return 1
}

check_http() {
  local auth_url="http://127.0.0.1:${PORT}/api/auth/status"
  local root_url="http://127.0.0.1:${PORT}/"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "$auth_url" >/dev/null 2>&1 && return 0
    curl -fsS --max-time 2 "$root_url" >/dev/null 2>&1
    return $?
  fi

  "$PYTHON_EXE" - <<PY >/dev/null 2>&1
import sys, urllib.request
urls = [${auth_url@Q}, ${root_url@Q}]
for url in urls:
    try:
        with urllib.request.urlopen(url, timeout=2):
            sys.exit(0)
    except Exception:
        continue
sys.exit(1)
PY
}

check_startup_log() {
  "$PYTHON_EXE" - <<PY >/dev/null 2>&1
from pathlib import Path
log_file = Path(${LOG_FILE@Q})
offset = int(${LOG_OFFSET})
if not log_file.exists():
    raise SystemExit(1)
try:
    with log_file.open("rb") as fh:
        fh.seek(offset)
        content = fh.read().decode("utf-8", errors="ignore")
except Exception:
    raise SystemExit(1)
markers = (
    "Application startup complete.",
    "Uvicorn running on",
)
raise SystemExit(0 if any(marker in content for marker in markers) else 1)
PY
}

PYTHON_EXE="$(resolve_python || true)"
if [[ -z "$PYTHON_EXE" || ! -x "$PYTHON_EXE" ]]; then
  echo "[ERROR] 未找到可用 Python。请先准备 conda 环境 '$ENV_NAME' 或项目 .venv。" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"
if [[ -f "$LOG_FILE" ]]; then
  LOG_OFFSET="$(wc -c < "$LOG_FILE" | tr -d '[:space:]')"
fi

cd "$ROOT"

echo "[INFO] 项目目录: $ROOT"
echo "[INFO] Python: $PYTHON_EXE"
echo "[INFO] 启动地址: http://127.0.0.1:${PORT}"
echo "[INFO] 日志文件: $LOG_FILE"

if [[ "$RESTART_EXISTING" == "1" ]]; then
  "$ROOT/stop_backend.sh" >/dev/null 2>&1 || true
fi

export HOST="$BIND_HOST"
export PORT="$PORT"
export APP_RELOAD="$APP_RELOAD"
export APP_CONDA_ENV="$ENV_NAME"
export APP_PYTHON="$PYTHON_EXE"

if command -v setsid >/dev/null 2>&1; then
  setsid "$PYTHON_EXE" main.py </dev/null >>"$LOG_FILE" 2>&1 &
else
  nohup "$PYTHON_EXE" main.py </dev/null >>"$LOG_FILE" 2>&1 &
fi
PID=$!
echo "$PID" >"$PID_FILE"

echo "[INFO] 已启动进程，PID=$PID，等待服务就绪..."
for ((i=1; i<=START_TIMEOUT; i++)); do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    echo "[ERROR] 后端进程启动失败，请查看日志: $LOG_FILE" >&2
    tail -n 80 "$LOG_FILE" || true
    exit 1
  fi

  if check_http; then
    echo "[OK] 后端已启动: http://127.0.0.1:${PORT}"
    exit 0
  fi

  if check_startup_log; then
    echo "[OK] 后端已启动（根据启动日志确认）: http://127.0.0.1:${PORT}"
    exit 0
  fi

  sleep 1
done

echo "[ERROR] 等待服务启动超时 (${START_TIMEOUT}s)，请查看日志: $LOG_FILE" >&2
exit 1
