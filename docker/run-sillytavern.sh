#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
ST_PORT="${ST_PORT:-8000}"
cd /apps/sillytavern

export NODE_ENV=production
export SILLYTAVERN_LISTEN=true
export SILLYTAVERN_WHITELISTMODE=false
export SILLYTAVERN_ENABLEFORWARDEDWHITELIST=false
export SILLYTAVERN_HOSTWHITELIST_ENABLED=false

mkdir -p "${DATA_ROOT}/sillytavern/config" "${DATA_ROOT}/sillytavern/data"

rm -rf config data
ln -sfn "${DATA_ROOT}/sillytavern/config" config
ln -sfn "${DATA_ROOT}/sillytavern/data" data
ln -sfn "${DATA_ROOT}/sillytavern/config/config.yaml" config.yaml

/opt/hub/docker/patch-sillytavern-config.sh

exec node server.js --listen --port "${ST_PORT}"