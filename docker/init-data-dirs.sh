#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/data}"

mkdir -p "${DATA_ROOT}/lumiverse"

# Lumiverse first-run marker (setup wizard skipped in hub mode)
touch "${DATA_ROOT}/lumiverse/.hub-initialized"

# HF runs as uid 1000 — avoid chown, just ensure writable
chmod -R u+rwX "${DATA_ROOT}" 2>/dev/null || true
