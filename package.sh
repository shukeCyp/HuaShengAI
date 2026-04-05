#!/usr/bin/env sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
WEB_DIST_DIR="${WEB_DIST_DIR:-$PROJECT_ROOT/app/web_dist}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing command: %s\n' "$1" >&2
    exit 1
  fi
}

require_cmd uv
require_cmd npm

printf '==> Sync Python dependencies with uv\n'
uv sync

FRONTEND_DIR="${FRONTEND_DIR:-$PROJECT_ROOT/frontend}" \
FRONTEND_BUILD_DIR="${FRONTEND_BUILD_DIR:-$PROJECT_ROOT/frontend/dist}" \
WEB_DIST_DIR="$WEB_DIST_DIR" \
  "$PROJECT_ROOT/scripts/build_frontend.sh"

printf '==> Build desktop bundle with PyInstaller\n'
uv run --with pyinstaller pyinstaller --noconfirm --clean "$PROJECT_ROOT/pyinstaller.spec"
