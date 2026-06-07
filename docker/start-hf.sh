#!/usr/bin/env bash
# HF Spaces: runs as UID 1000, nginx on :7860 (WebSocket-safe), no root.
set -uo pipefail

echo "[hub] HF start $(date -Is)" >&2

DATA_ROOT="${DATA_ROOT:-/data}"
export DATA_ROOT

mkdir -p "${DATA_ROOT}" "${DATA_ROOT}/.pids" /tmp 2>/dev/null || true
chmod -R u+rwX "${DATA_ROOT}" 2>/dev/null || true

/opt/hub/docker/init-data-dirs.sh 2>&1 || echo "[hub] warn: init-data-dirs" >&2
/opt/hub/docker/link-shared-data.sh 2>&1 || true
/opt/hub/scripts/sync-shared-data.sh 2>&1 || true

ACTIVE="${ACTIVE_APP:-sillytavern}"
[[ -f "${DATA_ROOT}/.active_app" ]] && ACTIVE="$(cat "${DATA_ROOT}/.active_app")"
echo "${ACTIVE}" > "${DATA_ROOT}/.active_app"

echo "[hub] starting hub-api on :7870" >&2
python3 /opt/hub/docker/hub-api.py >&2 &
HUB_API_PID=$!

echo "[hub] booting frontend: ${ACTIVE}" >&2
/opt/hub/docker/switch-app.sh "${ACTIVE}" 2>&1 || echo "[hub] warn: switch-app" >&2

(while true; do sleep 300; /opt/hub/scripts/sync-shared-data.sh || true; done) >&2 &

echo "[hub] nginx on :${HUB_PORT:-7860}" >&2
exec nginx -c /opt/hub/docker/nginx.conf -g 'daemon off;'