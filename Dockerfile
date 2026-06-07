# =============================================================================
# AI Frontends Hub — Hugging Face Space (self-contained, paste-safe)
#
# Works when you ONLY have this Dockerfile in the Space (no other files needed).
# Clones hub scripts from: https://github.com/Sexlovr/ai-hub-frontend
#
# HF setup:
#   1. New Space → Docker SDK
#   2. Paste this Dockerfile + README.md (with yaml frontmatter below)
#   3. Settings → Persistent storage → mount at /data
#   4. Secret: OWNER_PASSWORD (for Lumiverse)
#
# Free tier: uses marinara:lite (smaller). Override build-arg for :latest on paid.
# =============================================================================

# ── Hub orchestration (clone — no local COPY needed) ──────────────────────────
FROM alpine:3.20 AS hub-src
ARG HUB_REPO=https://github.com/Sexlovr/ai-hub-frontend.git
ARG HUB_REF=main
RUN apk add --no-cache git \
    && git clone --depth 1 --branch "${HUB_REF}" "${HUB_REPO}" /hub

# ── SillyTavern ───────────────────────────────────────────────────────────────
FROM ghcr.io/sillytavern/sillytavern:latest AS sillytavern

# ── Marinara (lite = ~60% smaller, fits HF free-tier build disk) ─────────────
ARG MARINARA_IMAGE=ghcr.io/pasta-devs/marinara-engine:lite
FROM ${MARINARA_IMAGE} AS marinara

# ── Lumiverse ─────────────────────────────────────────────────────────────────
FROM oven/bun:1-slim AS lumiverse-build
ARG LUMIVERSE_REPO=https://github.com/prolix-oc/Lumiverse.git
ARG LUMIVERSE_REF=main
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "${LUMIVERSE_REF}" "${LUMIVERSE_REPO}" . \
    && sed -i 's/c.req.header("host")/c.req.header("x-forwarded-host") || c.req.header("host")/g' src/app.ts \
    && sed -i 's/`http:\/\/${host}`/`${(c.req.header("x-forwarded-proto") || "http")}:\/\/${host}`/g' src/app.ts || true
WORKDIR /build/frontend
RUN bun install --frozen-lockfile 2>/dev/null || bun install \
    && bun run build \
    && rm -rf node_modules
WORKDIR /build
RUN bun install --production --frozen-lockfile 2>/dev/null || bun install --production \
    && rm -rf /root/.bun/install/cache 2>/dev/null || true

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM node:24-bookworm-slim

LABEL org.opencontainers.image.source="https://github.com/Sexlovr/ai-hub-frontend"

RUN apt-get update && apt-get install -y --no-install-recommends \
      nginx supervisor tini curl ca-certificates rsync inotify-tools python3 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && mkdir -p /var/log/supervisor /run/nginx /data \
    && chown -R www-data:www-data /var/log/nginx /run/nginx

COPY --from=oven/bun:1-slim /usr/local/bin/bun /usr/local/bin/bun
COPY --from=hub-src /hub/docker /opt/hub/docker/
COPY --from=hub-src /hub/scripts /opt/hub/scripts/
COPY --from=hub-src /hub/config /opt/hub/config/
COPY --from=hub-src /hub/public /opt/hub/public/
COPY --from=sillytavern /home/node/app /apps/sillytavern
COPY --from=marinara /app /apps/marinara
COPY --from=marinara /usr/local/bin/marinara-docker-entrypoint.mjs /usr/local/bin/marinara-docker-entrypoint.mjs
COPY --from=lumiverse-build /build /apps/lumiverse

RUN chmod +x /opt/hub/docker/*.sh /opt/hub/scripts/*.sh \
    && chown -R node:node /apps/sillytavern /apps/marinara /data \
    && rm -rf /apps/sillytavern/.git /apps/marinara/.git 2>/dev/null || true

ENV DATA_ROOT=/data
ENV HUB_PORT=7860
ENV ACTIVE_APP=sillytavern
ENV ST_PORT=8000
ENV LUMIVERSE_PORT=7861
ENV MARINARA_PORT=7862
ENV NODE_ENV=production
ENV TRUST_ANY_ORIGIN=true

VOLUME ["/data"]
EXPOSE 7860

# No HEALTHCHECK — HF free tier kills containers that fail health probes during slow cold-start

ENTRYPOINT ["/opt/hub/docker/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/opt/hub/docker/supervisord.conf"]