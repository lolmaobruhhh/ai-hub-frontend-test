#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
LUMIVERSE_PORT="${LUMIVERSE_PORT:-7861}"
cd /apps/lumiverse

export NODE_ENV=production
export PORT="${LUMIVERSE_PORT}"
export DATA_DIR="${DATA_ROOT}/lumiverse"
export FRONTEND_DIR=/apps/lumiverse/frontend/dist
export TRUST_ANY_ORIGIN=true

# First run: set OWNER_PASSWORD secret in HF Space settings before switching to Lumiverse.
mkdir -p "${DATA_DIR}"

exec bun run src/index.ts