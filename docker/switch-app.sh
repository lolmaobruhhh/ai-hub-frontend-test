#!/usr/bin/env bash
set -euo pipefail

APP="${1:-}"
DATA_ROOT="${DATA_ROOT:-/data}"
PID_DIR="${DATA_ROOT}/.pids"
mkdir -p "${PID_DIR}"

if [[ -z "${APP}" ]]; then
  echo "usage: switch-app.sh <sillytavern|lumiverse|marinara>" >&2
  exit 1
fi

case "${APP}" in
  sillytavern|lumiverse|marinara) ;;
  *) echo "unknown app: ${APP}" >&2; exit 1 ;;
esac

echo "${APP}" > "${DATA_ROOT}/.active_app"

stop_one() {
  local name="$1"
  local pidfile="${PID_DIR}/${name}.pid"
  if [[ -f "${pidfile}" ]]; then
    kill "$(cat "${pidfile}")" 2>/dev/null || true
    rm -f "${pidfile}"
  fi
}

stop_one sillytavern
stop_one lumiverse
stop_one marinara

start_one() {
  local name="$1"
  local script="/opt/hub/docker/run-${name}.sh"
  nohup bash "${script}" > "${DATA_ROOT}/${name}.log" 2>&1 &
  echo $! > "${PID_DIR}/${name}.pid"
  echo "[hub] started ${name} pid $(cat "${PID_DIR}/${name}.pid")" >&2
}

case "${APP}" in
  sillytavern) start_one sillytavern ;;
  lumiverse)
    /opt/hub/docker/install-lumiverse.sh || true
    start_one lumiverse
    ;;
  marinara) start_one marinara ;;
esac

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

echo "[hub] switched to ${APP} on internal port ${PORT}" >&2
sleep 2