#!/usr/bin/env bash
set -euo pipefail

APP="${1:-}"
DATA_ROOT="${DATA_ROOT:-/data}"

if [[ -z "${APP}" ]]; then
  echo "usage: switch-app.sh <sillytavern|lumiverse|marinara>" >&2
  exit 1
fi

case "${APP}" in
  sillytavern|lumiverse|marinara) ;;
  *)
    echo "unknown app: ${APP}" >&2
    exit 1
    ;;
esac

echo "${APP}" > "${DATA_ROOT}/.active_app"

supervisorctl stop sillytavern lumiverse marinara 2>/dev/null || true
supervisorctl start "${APP}"

PORT="8000"
case "${APP}" in
  sillytavern) PORT="${ST_PORT:-8000}" ;;
  lumiverse)   PORT="${LUMIVERSE_PORT:-7861}" ;;
  marinara)    PORT="${MARINARA_PORT:-7862}" ;;
esac

cat > /opt/hub/docker/upstream.conf <<EOF
upstream active_backend {
    server 127.0.0.1:${PORT};
}
EOF

nginx -s reload -c /opt/hub/docker/nginx.conf 2>/dev/null || supervisorctl restart nginx

echo "[hub] switched to ${APP} on internal port ${PORT}"