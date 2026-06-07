#!/usr/bin/env bash
set -uo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
LUMIVERSE_PORT="${LUMIVERSE_PORT:-7861}"
cd /apps/lumiverse

export NODE_ENV=production
export PORT="${LUMIVERSE_PORT}"
export DATA_DIR="${DATA_ROOT}/lumiverse"
export FRONTEND_DIR=/apps/lumiverse/frontend/dist
export TRUST_ANY_ORIGIN=true

# Required for BetterAuth login behind HF HTTPS proxy.
# Set in HF Secrets: PUBLIC_ORIGIN=https://your-space.hf.space
if [[ -n "${PUBLIC_ORIGIN:-}" ]]; then
  export AUTH_BASE_URL="${PUBLIC_ORIGIN}"
  echo "[lumiverse] AUTH_BASE_URL=${AUTH_BASE_URL}" >&2
else
  echo "[lumiverse] WARN: set PUBLIC_ORIGIN=https://YOUR-SPACE.hf.space in HF Secrets for login" >&2
fi

mkdir -p "${DATA_DIR}"
exec bun run src/index.ts