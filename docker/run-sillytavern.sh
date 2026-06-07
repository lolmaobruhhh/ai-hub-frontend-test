#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
ST_PORT="${ST_PORT:-8000}"
cd /apps/sillytavern

export NODE_ENV=production

mkdir -p "${DATA_ROOT}/sillytavern/config" "${DATA_ROOT}/sillytavern/data"

# Wire persistent volumes into the app tree
rm -rf config data
ln -sfn "${DATA_ROOT}/sillytavern/config" config
ln -sfn "${DATA_ROOT}/sillytavern/data" data
ln -sfn "${DATA_ROOT}/sillytavern/config/config.yaml" config.yaml

if [[ ! -f config/config.yaml ]]; then
  cp default/config.yaml config/config.yaml 2>/dev/null \
    || cp /opt/hub/config/sillytavern-config.yaml config/config.yaml
fi

exec node server.js --listen --port "${ST_PORT}"