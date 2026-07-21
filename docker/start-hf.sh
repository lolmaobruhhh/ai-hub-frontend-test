#!/usr/bin/env bash
set -uo pipefail

echo "[hub] HF start $(date -Is)" >&2

DATA_ROOT="${DATA_ROOT:-/data}"
export DATA_ROOT
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

if [[ -z "${PUBLIC_ORIGIN:-}" ]]; then
  resolved="$(bash /opt/hub/docker/resolve-public-origin.sh 2>/dev/null || true)"
  if [[ -n "${resolved}" ]]; then
    export PUBLIC_ORIGIN="${resolved}"
  fi
fi

mkdir -p "${DATA_ROOT}" "${DATA_ROOT}/.pids" 2>/dev/null || true
chmod -R u+rwX "${DATA_ROOT}" 2>/dev/null || true

/opt/hub/docker/init-data-dirs.sh 2>&1 || echo "[hub] warn: init-data-dirs" >&2

echo "[hub] starting lumiverse" >&2
/opt/hub/docker/start-all-apps.sh 2>&1 || echo "[hub] warn: start-all-apps" >&2

BACKEND_PORT="${LUMIVERSE_PORT:-7861}"
port_up() {
  (echo >/dev/tcp/127.0.0.1/"${BACKEND_PORT}") >/dev/null 2>&1
}

WAIT_MAX=180
echo "[hub] waiting for backend :${BACKEND_PORT} (up to ${WAIT_MAX}s)" >&2
ready=0
for i in $(seq 1 "${WAIT_MAX}"); do
  if port_up; then
    echo "[hub] backend ready on :${BACKEND_PORT} (after ${i}s)" >&2
    ready=1
    break
  fi
  if (( i % 10 == 0 )); then
    echo "[hub] still waiting for :${BACKEND_PORT} (${i}s)..." >&2
  fi
  sleep 1
done

if [[ "${ready}" -eq 0 ]]; then
  echo "[hub] ERROR: backend :${BACKEND_PORT} never opened — check [lumiverse] lines above" >&2
fi

echo "[hub] gateway on :${HUB_PORT:-7860} (lumiverse=/ discover=/discover)" >&2
exec python3 /opt/hub/docker/hub-gateway.py
