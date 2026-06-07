#!/usr/bin/env bash
# Sync canonical shared library -> Marinara + Lumiverse staging import dirs.
# SillyTavern uses live symlinks and does not need copying.
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
SHARED="${DATA_ROOT}/shared"

echo "[sync] $(date -Is) syncing shared library"

rsync -a --delete "${SHARED}/characters/" "${DATA_ROOT}/marinara/storage/import-staging/characters/" 2>/dev/null || true
rsync -a --delete "${SHARED}/characters/" "${DATA_ROOT}/lumiverse/import-staging/characters/" 2>/dev/null || true
rsync -a --delete "${SHARED}/world_info/" "${DATA_ROOT}/marinara/storage/import-staging/world_info/" 2>/dev/null || true
rsync -a --delete "${SHARED}/world_info/" "${DATA_ROOT}/lumiverse/import-staging/world_info/" 2>/dev/null || true
rsync -a "${SHARED}/connections/" "${DATA_ROOT}/marinara/storage/import-staging/connections/" 2>/dev/null || true
rsync -a "${SHARED}/connections/" "${DATA_ROOT}/lumiverse/import-staging/connections/" 2>/dev/null || true

# Optional: auto-import into Marinara when ADMIN_SECRET + API are available
if [[ -n "${ADMIN_SECRET:-}" ]]; then
  MARINARA_PORT="${MARINARA_PORT:-7862}"
  if curl -fsS "http://127.0.0.1:${MARINARA_PORT}/api/health" >/dev/null 2>&1; then
    curl -fsS -X POST "http://127.0.0.1:${MARINARA_PORT}/api/import/sillytavern/scan" \
      -H "X-Admin-Secret: ${ADMIN_SECRET}" \
      -H "Content-Type: application/json" \
      -d "{\"root\":\"${SHARED}\"}" >/dev/null 2>&1 || true
  fi
fi

echo "[sync] done"