#!/usr/bin/env bash
# Point nginx at the chosen frontend. All three backends stay running.
set -uo pipefail

APP="${1:-}"
DATA_ROOT="${DATA_ROOT:-/data}"

if [[ -z "${APP}" ]]; then
  echo "usage: switch-app.sh <sillytavern|lumiverse|marinara>" >&2
  exit 1
fi

case "${APP}" in
  sillytavern|lumiverse|marinara) ;;
  *) echo "unknown app: ${APP}" >&2; exit 1 ;;
esac

port_for() {
  case "$1" in
    sillytavern) echo "${ST_PORT:-8000}" ;;
    lumiverse)   echo "${LUMIVERSE_PORT:-7861}" ;;
    marinara)    echo "${MARINARA_PORT:-7862}" ;;
  esac
}

PREV_APP=""
if [[ -f "${DATA_ROOT}/.active_app" ]]; then
  PREV_APP="$(cat "${DATA_ROOT}/.active_app")"
fi

# Export from the previously active app before changing routes.
if [[ -n "${PREV_APP}" && "${PREV_APP}" != "${APP}" ]]; then
  HUB_SYNC_EXPORT="${PREV_APP}" python3 /opt/hub/scripts/hub-sync-import.py 2>&1 || true
fi

echo "${APP}" > "${DATA_ROOT}/.active_app"

/opt/hub/docker/start-all-apps.sh 2>&1 || true

PORT="$(port_for "${APP}")"

cat > /opt/hub/docker/upstream.conf <<EOF
upstream active_backend {
    server 127.0.0.1:${PORT};
}
EOF

if nginx -s reload -c /opt/hub/docker/nginx.conf 2>/dev/null; then
  echo "[hub] nginx reloaded → ${APP} on :${PORT}" >&2
else
  echo "[hub] nginx reload skipped (not running yet)" >&2
fi

/opt/hub/scripts/sync-shared-data.sh 2>&1 || echo "[hub] warn: sync-shared-data" >&2

echo "[hub] switched to ${APP} on internal port ${PORT}" >&2