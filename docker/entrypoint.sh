#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
export DATA_ROOT

echo "[hub] Initializing data layout under ${DATA_ROOT}"
/opt/hub/docker/init-data-dirs.sh

echo "[hub] Linking shared library into each frontend"
/opt/hub/docker/link-shared-data.sh

echo "[hub] Running initial shared-data sync"
/opt/hub/scripts/sync-shared-data.sh || true

# Start background watcher for live character/lorebook sync
if command -v inotifywait >/dev/null 2>&1; then
  (
    while inotifywait -r -e create,modify,close_write,moved_to,delete \
      "${DATA_ROOT}/shared/characters" \
      "${DATA_ROOT}/shared/world_info" \
      "${DATA_ROOT}/shared/connections" 2>/dev/null; do
      /opt/hub/scripts/sync-shared-data.sh || true
    done
  ) &
fi

# Restore last active app if persisted
if [[ -f "${DATA_ROOT}/.active_app" ]]; then
  export ACTIVE_APP
  ACTIVE_APP="$(cat "${DATA_ROOT}/.active_app")"
  export ACTIVE_APP
fi

echo "[hub] Active frontend: ${ACTIVE_APP:-sillytavern}"
echo "${ACTIVE_APP:-sillytavern}" > "${DATA_ROOT}/.active_app"

exec tini -- "$@"