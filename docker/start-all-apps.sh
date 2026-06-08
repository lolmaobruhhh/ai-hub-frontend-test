#!/usr/bin/env bash
# Start all three frontends if not already listening (always-on mode).
# Launch in parallel — SillyTavern init can take minutes; don't block the others.
set -uo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
PID_DIR="${DATA_ROOT}/.pids"
LOG_DIR="${DATA_ROOT}/.logs"
mkdir -p "${PID_DIR}" "${LOG_DIR}"

port_up() {
  local port="$1"
  (echo >/dev/tcp/127.0.0.1/"${port}") >/dev/null 2>&1
}

wait_for() {
  local name="$1"
  local port="$2"
  local max="$3"
  for i in $(seq 1 "${max}"); do
    if port_up "${port}"; then
      echo "[hub] ${name} ready on :${port} (after ${i}s)" >&2
      return 0
    fi
    sleep 1
  done
  echo "[hub] WARN: ${name} not ready on :${port} after ${max}s" >&2
  return 1
}

launch_one() {
  local name="$1"
  local port="$2"
  local script="/opt/hub/docker/run-${name}.sh"
  local log="${LOG_DIR}/${name}.log"
  local pidfile="${PID_DIR}/${name}.pid"
  local logpidfile="${PID_DIR}/${name}-log.pid"

  if port_up "${port}"; then
    echo "[hub] ${name} already up on :${port}" >&2
    return 0
  fi

  if [[ -f "${logpidfile}" ]]; then
    kill "$(cat "${logpidfile}")" 2>/dev/null || true
    rm -f "${logpidfile}"
  fi
  if [[ -f "${pidfile}" ]]; then
    kill "$(cat "${pidfile}")" 2>/dev/null || true
    rm -f "${pidfile}"
  fi

  : > "${log}"
  setsid bash -c "exec bash \"${script}\"" >> "${log}" 2>&1 &
  echo $! > "${pidfile}"

  tail -n 0 -f "${log}" 2>/dev/null | sed -u "s/^/[${name}] /" >&2 &
  echo $! > "${logpidfile}"

  echo "[hub] started ${name} pid $(cat "${pidfile}")" >&2
}

# Launch all three at once, then wait for each port.
launch_one sillytavern "${ST_PORT:-8000}" &
p1=$!
launch_one lumiverse   "${LUMIVERSE_PORT:-7861}" &
p2=$!
launch_one marinara    "${MARINARA_PORT:-7862}" &
p3=$!
wait "${p1}" "${p2}" "${p3}" 2>/dev/null || true

wait_for sillytavern "${ST_PORT:-8000}" 300 || true
wait_for lumiverse   "${LUMIVERSE_PORT:-7861}" 90 || true
wait_for marinara    "${MARINARA_PORT:-7862}" 60 || true