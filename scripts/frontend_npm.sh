#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"
MIN_NODE_VERSION="${MIN_NODE_VERSION:-20.19.0}"
BUNDLED_NODE_BIN="$ROOT/.tools/node20/bin"

version_ge() {
  local current="$1"
  local required="$2"
  [[ "$(printf '%s\n%s\n' "$required" "$current" | sort -V | head -n 1)" == "$required" ]]
}

resolve_node_bin() {
  local node_bin=""
  local version=""

  if [[ -x "$BUNDLED_NODE_BIN/node" && -x "$BUNDLED_NODE_BIN/npm" ]]; then
    version="$("$BUNDLED_NODE_BIN/node" -p 'process.versions.node')"
    if version_ge "$version" "$MIN_NODE_VERSION"; then
      echo "$BUNDLED_NODE_BIN"
      return 0
    fi
  fi

  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    node_bin="$(dirname "$(command -v node)")"
    version="$(node -p 'process.versions.node')"
    if version_ge "$version" "$MIN_NODE_VERSION"; then
      echo "$node_bin"
      return 0
    fi
  fi

  return 1
}

NODE_BIN="$(resolve_node_bin || true)"
if [[ -z "$NODE_BIN" ]]; then
  echo "[ERROR] 未找到满足要求的 Node.js。当前前端构建需要 Node >= ${MIN_NODE_VERSION}。" >&2
  echo "[ERROR] 可使用项目内置 Node: $BUNDLED_NODE_BIN" >&2
  exit 1
fi

export PATH="$NODE_BIN:$PATH"

echo "[INFO] Frontend directory: $FRONTEND_DIR"
echo "[INFO] Node: $(command -v node) ($(node -p 'process.versions.node'))"
echo "[INFO] npm:  $(command -v npm) ($(npm -v))"

cd "$FRONTEND_DIR"

if [[ $# -eq 0 ]]; then
  set -- run build
fi

npm "$@"
