#!/usr/bin/env bash
# BetterAuth behind the hub gateway.
#
# History: BetterAuth <=1.5 (better-call 1.3.x) matched routes with a lenient
# split-anywhere basePath, so we prepended X-Forwarded-Prefix to the handler
# URL to hand BetterAuth the public subpath.
#
# Lumiverse 1.2.0 (BetterAuth 1.7.2 / better-call 1.4.0) matches routes with a
# strict startsWith(basePath + "/") — a prefix-prepended path 404s. The hub
# gateway already strips /apps/<app> before proxying and the 1.2.0 handler
# natively honors X-Forwarded-Proto/Host, so with AUTH_BASE_URL at the root
# origin the unmodified code routes correctly both as the active root app and
# via the /apps/lumiverse subpath. For 1.2.0+ this script therefore only
# VERIFIES the handler shape (fail the build loudly if upstream changes
# again); the legacy prepend below is kept for pre-1.2.0 images.
set -euo pipefail

APP_TS="${1:-/apps/lumiverse/src/app.ts}"
if [[ ! -f "${APP_TS}" ]]; then
  echo "[hub] lumiverse app.ts not found — skip auth patch" >&2
  exit 0
fi

python3 - "${APP_TS}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "fwdPrefix" in text and "x-forwarded-prefix" in text:
    print("[hub] lumiverse auth patch already applied", flush=True)
    raise SystemExit(0)

# --- Lumiverse 1.2.0+ (BetterAuth 1.7): verify shape, no rewrite needed ---
# host/proto are header-read checks, not exact lines, because the Dockerfile's
# split-first seds rewrite those lines after this script runs at build time;
# boot-time re-runs must verify cleanly against the already-seded file.
checks = (
    ("const pathname = rewriteLegacySsoCallbackPath(url.pathname);", "rewriteLegacySsoCallbackPath line"),
    ("const rewritten = new URL(pathname + url.search, origin);", "computed-origin rewritten URL line"),
    ('c.req.header("x-forwarded-host")', "x-forwarded-host header read"),
    ('c.req.header("x-forwarded-proto")', "x-forwarded-proto header read"),
)
missing = [label for needle, label in checks if needle not in text]
if not missing:
    print("[hub] lumiverse 1.2.0 auth handler shape verified — upstream honors forwarded headers, no rewrite needed", flush=True)
    raise SystemExit(0)

# --- Pre-1.2.0 images: prepend X-Forwarded-Prefix (lenient-router era) ---
# Backslash via chr(92): this heredoc contains no literal backslashes.
BS = chr(92)
FWD_DECL = 'const fwdPrefix = (c.req.header("x-forwarded-prefix") || "").replace(/' + BS + '/$/, "");'
LEGACY_REWRITTEN = 'const rewritten = new URL((fwdPrefix + url.pathname).replace(/' + BS + '/' + BS + '/+/g, "/") + url.search, `${proto}://${host}`);'

for old in (
    "const rewritten = new URL(url.pathname + url.search, `${proto}://${host}`);",
    "const rewritten=new URL(url.pathname+url.search,`${proto}://${host}`);",
):
    if old in text:
        t = text.replace(old, FWD_DECL + "\n    " + LEGACY_REWRITTEN, 1)
        path.write_text(t, encoding="utf-8")
        print("[hub] patched lumiverse BetterAuth URL rewrite (legacy shape) for subpath hub", flush=True)
        raise SystemExit(0)

print("[hub] ERROR: lumiverse auth handler shape not recognized; missing 1.2.0 anchors: " + "; ".join(missing), flush=True)
print("[hub] ERROR: lumiverse auth rewrite pattern not found in app.ts", flush=True)
raise SystemExit(1)
PY
