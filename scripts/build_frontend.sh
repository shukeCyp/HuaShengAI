#!/usr/bin/env sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$PROJECT_ROOT/frontend}"
FRONTEND_BUILD_DIR="${FRONTEND_BUILD_DIR:-$FRONTEND_DIR/dist}"
WEB_DIST_DIR="${WEB_DIST_DIR:-$PROJECT_ROOT/app/web_dist}"

printf '==> Install frontend dependencies\n'
npm --prefix "$FRONTEND_DIR" ci

printf '==> Build Vue frontend\n'
npm --prefix "$FRONTEND_DIR" run build

printf '==> Copy built assets into %s\n' "$WEB_DIST_DIR"
mkdir -p "$WEB_DIST_DIR"
find "$WEB_DIST_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -R "$FRONTEND_BUILD_DIR/." "$WEB_DIST_DIR/"
