#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"
ST_USER_DIR="${DATA_ROOT}/sillytavern/data/default-user"

mkdir -p "${ST_USER_DIR}/characters" "${ST_USER_DIR}/worlds"

# SillyTavern reads characters + world_info directly from shared folders
link_or_replace() {
  local target="$1"
  local source="$2"
  mkdir -p "$(dirname "${target}")" "${source}"
  if [[ -L "${target}" ]]; then
    rm -f "${target}"
  elif [[ -d "${target}" ]]; then
    # Merge any existing files into shared, then replace with symlink
    rsync -a "${target}/" "${source}/" 2>/dev/null || true
    rm -rf "${target}"
  fi
  ln -sfn "${source}" "${target}"
}

link_or_replace "${ST_USER_DIR}/characters" "${DATA_ROOT}/shared/characters"
link_or_replace "${ST_USER_DIR}/worlds" "${DATA_ROOT}/shared/world_info"

# Marinara + Lumiverse keep native storage but sync FROM shared (see sync script)
mkdir -p "${DATA_ROOT}/marinara/storage/import-staging/characters"
mkdir -p "${DATA_ROOT}/marinara/storage/import-staging/world_info"
mkdir -p "${DATA_ROOT}/lumiverse/import-staging/characters"
mkdir -p "${DATA_ROOT}/lumiverse/import-staging/world_info"