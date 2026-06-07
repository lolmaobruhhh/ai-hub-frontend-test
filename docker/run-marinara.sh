#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
MARINARA_PORT="${MARINARA_PORT:-7862}"
cd /apps/marinara

export NODE_ENV=production
export PORT="${MARINARA_PORT}"
export HOST=0.0.0.0
export DATA_DIR="${DATA_ROOT}/marinara"
export FILE_STORAGE_DIR="${DATA_ROOT}/marinara/storage"
export MARINARA_ENV_FILE="${DATA_ROOT}/marinara/.env"
export MARINARA_DOCKER=true
export ALLOW_UNAUTHENTICATED_REMOTE=true
export IMPORT_ALLOWED_ROOTS="${DATA_ROOT}/shared"

exec node /usr/local/bin/marinara-docker-entrypoint.mjs node packages/server/dist/index.js