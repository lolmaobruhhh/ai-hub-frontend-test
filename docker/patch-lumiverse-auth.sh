#!/usr/bin/env bash
# BetterAuth baseURL includes /apps/lumiverse — auth handler must rewrite requests
# with X-Forwarded-Prefix or sign-in returns 404 behind the hub gateway.
set -uo pipefail

APP_TS="/apps/lumiverse/src/app.ts"
if [[ ! -f "${APP_TS}" ]]; then
  echo "[hub] lumiverse app.ts not found — skip auth patch" >&2
  exit 0
fi

python3 - "${APP_TS}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = 'const rewritten = new URL(url.pathname + url.search, `${proto}://${host}`);'
replacement = (
    'const fwdPrefix = (c.req.header("x-forwarded-prefix") || "").replace(/\\/$/, "");\n'
    '    const rewritten = new URL((fwdPrefix + url.pathname).replace(/\\/\\/+/g, "/") + url.search, `${proto}://${host}`);'
)

if needle not in text:
    if "x-forwarded-prefix" in text and "fwdPrefix" in text:
        print("[hub] lumiverse auth patch already applied", flush=True)
    else:
        print("[hub] WARN: lumiverse auth rewrite pattern not found — manual check needed", flush=True)
    raise SystemExit(0)

path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
print("[hub] patched lumiverse BetterAuth URL rewrite for subpath hub", flush=True)
PY