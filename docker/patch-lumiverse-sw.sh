#!/usr/bin/env bash
# Lumiverse's PWA service worker serves cached index.html for navigations to
# /hub (not in its denylist). Patch the built sw.js so /hub reaches nginx.
set -uo pipefail

SW="/apps/lumiverse/frontend/dist/sw.js"
[[ -f "${SW}" ]] || { echo "[hub] lumiverse sw.js not found — skip SW patch" >&2; exit 0; }

python3 - "${SW}" <<'PY'
import re, sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
if re.search(r"/\\hub", text):
    print("[hub] lumiverse sw.js already patched", flush=True)
    sys.exit(0)

# inject denylist entries right after the opening bracket
patched, n = re.subn(
    r"(denylist:\s*\[)",
    r"\1/^\\/hub/,/^\\/hub\\.html/,",
    text,
    count=1,
)
if n == 0:
    # minified / alternate formatting
    patched, n = re.subn(
        r"(\[)(/\\^\\/api/)",
        r"\1/^\\/hub/,/^\\/hub\\.html/,\2",
        text,
        count=1,
    )

if n == 0:
    print("[hub] WARN: could not patch lumiverse sw.js denylist", flush=True)
    sys.exit(0)

path.write_text(patched)
print("[hub] patched lumiverse sw.js — /hub bypasses PWA navigation cache", flush=True)
PY