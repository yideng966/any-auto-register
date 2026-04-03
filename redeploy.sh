#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-${DEPLOY_MODE:-local}}"
ENV_NAME="${APP_CONDA_ENV:-any-auto-register}"
REMOTE="${GIT_REMOTE:-origin}"
EXPECTED_REMOTE_URL="${GIT_URL:-https://github.com/yideng966/any-auto-register.git}"
FORCE_RESET="${FORCE_RESET:-0}"
INSTALL_BACKEND_DEPS="${INSTALL_BACKEND_DEPS:-auto}"
INSTALL_BROWSER_DEPS="${INSTALL_BROWSER_DEPS:-0}"
BUILD_FRONTEND="${BUILD_FRONTEND:-auto}"
START_AFTER_DEPLOY="${START_AFTER_DEPLOY:-1}"
OLD_HEAD=""
NEW_HEAD=""
FRONTEND_NPM_SH="$ROOT/scripts/frontend_npm.sh"

cd "$ROOT"

usage() {
  cat <<USAGE
用法:
  ./redeploy.sh [local|docker]

常用环境变量:
  APP_PYTHON=$ROOT/.venv/bin/python  指定当前目录 Python，优先级最高
  APP_CONDA_ENV=any-auto-register   指定 conda 环境名
  GIT_URL=$EXPECTED_REMOTE_URL      指定项目 Git 地址
  FORCE_RESET=1                     强制重置到远端分支（会覆盖本地已跟踪修改）
  INSTALL_BACKEND_DEPS=auto         auto/1/0；仅 requirements.txt 变更时安装
  INSTALL_BROWSER_DEPS=0            默认跳过 playwright/camoufox 重装
  BUILD_FRONTEND=auto               auto/1/0；仅前端变更时构建
  START_AFTER_DEPLOY=0              只部署不启动
USAGE
}

normalize_git_url() {
  local url="${1:-}"
  url="${url%.git}"
  url="${url%/}"
  echo "$url"
}

ensure_git_remote() {
  local current_url=""

  if git remote get-url "$REMOTE" >/dev/null 2>&1; then
    current_url="$(git remote get-url "$REMOTE" 2>/dev/null || true)"
    if [[ "$(normalize_git_url "$current_url")" != "$(normalize_git_url "$EXPECTED_REMOTE_URL")" ]]; then
      echo "[INFO] 更新 Git 远端地址: $REMOTE -> $EXPECTED_REMOTE_URL"
      git remote set-url "$REMOTE" "$EXPECTED_REMOTE_URL"
    fi
  else
    echo "[INFO] 新增 Git 远端地址: $REMOTE -> $EXPECTED_REMOTE_URL"
    git remote add "$REMOTE" "$EXPECTED_REMOTE_URL"
  fi
}

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

ensure_clean_git() {
  if git diff --quiet --ignore-submodules -- && git diff --cached --quiet --ignore-submodules --; then
    return 0
  fi

  if [[ "$FORCE_RESET" == "1" ]]; then
    echo "[WARN] 检测到已跟踪文件存在修改，稍后将强制重置到远端版本"
    return 0
  fi

  echo "[ERROR] 检测到已跟踪文件有本地修改，已停止自动拉取。" >&2
  echo "[ERROR] 如确认覆盖本地修改，请使用: FORCE_RESET=1 ./redeploy.sh $MODE" >&2
  git status --short
  exit 1
}

git_update() {
  local branch
  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [[ -z "$branch" ]]; then
    echo "[ERROR] 当前不在本地分支上，无法自动 pull。请先 checkout 到具体分支。" >&2
    exit 1
  fi

  echo "[INFO] 拉取远端代码: $REMOTE/$branch"
  git fetch --prune "$REMOTE"

  if [[ "$FORCE_RESET" == "1" ]]; then
    git reset --hard "$REMOTE/$branch"
  else
    git pull --ff-only "$REMOTE" "$branch"
  fi
}

has_git_changes() {
  [[ -n "$OLD_HEAD" && -n "$NEW_HEAD" && "$OLD_HEAD" != "$NEW_HEAD" ]]
}

changed_between() {
  local pathspec=("$@")
  has_git_changes || return 1
  git diff --name-only "$OLD_HEAD" "$NEW_HEAD" -- "${pathspec[@]}" | grep -q .
}

deploy_local() {
  local python_exe
  local should_install_backend=0
  local should_build_frontend=0
  local should_npm_install=0
  python_exe="$(resolve_python || true)"
  if [[ -z "$python_exe" || ! -x "$python_exe" ]]; then
    echo "[ERROR] 未找到可用 Python。请先准备 conda 环境 '$ENV_NAME' 或项目 .venv。" >&2
    exit 1
  fi

  echo "[INFO] 使用 Python: $python_exe"
  if [[ "$python_exe" == "$ROOT/.venv/bin/python" ]]; then
    echo "[INFO] 已锁定当前目录虚拟环境: $ROOT/.venv"
  fi
  export APP_PYTHON="$python_exe"

  case "$INSTALL_BACKEND_DEPS" in
    1|true|yes)
      should_install_backend=1
      ;;
    auto)
      if changed_between requirements.txt; then
        should_install_backend=1
      fi
      ;;
    0|false|no)
      ;;
    *)
      echo "[ERROR] INSTALL_BACKEND_DEPS 只支持 auto/1/0" >&2
      exit 1
      ;;
  esac

  if [[ "$should_install_backend" == "1" ]]; then
    echo "[STEP] 安装/更新后端依赖"
    "$python_exe" -m pip install -r requirements.txt
  else
    echo "[STEP] 跳过后端依赖安装（requirements.txt 无变更）"
  fi

  if [[ "$INSTALL_BROWSER_DEPS" == "1" ]]; then
    echo "[STEP] 安装/更新浏览器依赖"
    "$python_exe" -m playwright install chromium
    "$python_exe" -m camoufox fetch
  fi

  case "$BUILD_FRONTEND" in
    1|true|yes)
      should_build_frontend=1
      should_npm_install=1
      ;;
    auto)
      if changed_between frontend; then
        should_build_frontend=1
      fi
      if changed_between frontend/package.json frontend/package-lock.json; then
        should_npm_install=1
      fi
      ;;
    0|false|no)
      ;;
    *)
      echo "[ERROR] BUILD_FRONTEND 只支持 auto/1/0" >&2
      exit 1
      ;;
  esac

  if [[ "$should_build_frontend" == "1" ]]; then
    if [[ ! -x "$FRONTEND_NPM_SH" ]]; then
      echo "[ERROR] 未找到前端构建脚本: $FRONTEND_NPM_SH" >&2
      exit 1
    fi
    echo "[STEP] 构建前端"
    (
      if [[ "$should_npm_install" == "1" ]]; then
        echo "[STEP] 检测到前端依赖变更，执行 npm install"
        "$FRONTEND_NPM_SH" install
      else
        echo "[STEP] 前端依赖无变更，跳过 npm install"
      fi
      "$FRONTEND_NPM_SH" run build
    )
  else
    echo "[STEP] 跳过前端构建（frontend/ 无变更）"
  fi

  if [[ "$START_AFTER_DEPLOY" == "1" ]]; then
    echo "[STEP] 重启后端"
    "$ROOT/start_backend.sh"
  fi
}

deploy_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] 未找到 docker 命令。" >&2
    exit 1
  fi

  echo "[STEP] 使用 Docker 重新部署"
  docker compose down --remove-orphans
  docker compose up -d --build
  docker compose ps
}

case "$MODE" in
  -h|--help|help)
    usage
    exit 0
    ;;
  local|docker)
    ;;
  *)
    echo "[ERROR] 不支持的模式: $MODE" >&2
    usage
    exit 1
    ;;
esac

echo "[INFO] 项目目录: $ROOT"
echo "[INFO] 部署模式: $MODE"

if [[ "$MODE" == "local" ]]; then
  echo "[STEP] 先停止当前后端服务"
  "$ROOT/stop_backend.sh" >/dev/null 2>&1 || true
fi

ensure_git_remote
ensure_clean_git
OLD_HEAD="$(git rev-parse HEAD)"
git_update
NEW_HEAD="$(git rev-parse HEAD)"

if has_git_changes; then
  echo "[INFO] 本次更新范围: $OLD_HEAD -> $NEW_HEAD"
else
  echo "[INFO] 本次拉取没有代码变化"
fi

if [[ "$MODE" == "docker" ]]; then
  deploy_docker
else
  deploy_local
fi

echo "[OK] 重新拉取并部署完成"
