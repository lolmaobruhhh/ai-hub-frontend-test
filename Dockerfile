# AI Frontends Hub — SillyTavern + Lumiverse + Marinara Engine on one HF Space

FROM ghcr.io/sillytavern/sillytavern:latest AS sillytavern
FROM ghcr.io/pasta-devs/marinara-engine:latest AS marinara

FROM oven/bun:1-slim AS lumiverse-build
ARG LUMIVERSE_REF=main
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${LUMIVERSE_REF}" https://github.com/prolix-oc/Lumiverse.git .

# Patch BetterAuth for HF reverse-proxy (x-forwarded-proto/host)
RUN sed -i 's/c.req.header("host")/c.req.header("x-forwarded-host") || c.req.header("host")/g' src/app.ts \
    && sed -i 's/`http:\/\/${host}`/`${(c.req.header("x-forwarded-proto") || "http")}:\/\/${host}`/g' src/app.ts || true

WORKDIR /build/frontend
RUN bun install --frozen-lockfile 2>/dev/null || bun install && bun run build
WORKDIR /build
RUN bun install --production --frozen-lockfile 2>/dev/null || bun install --production

# Runtime: Node base (ST + Marinara) + Bun (Lumiverse) + nginx
FROM node:24-bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      nginx supervisor tini curl ca-certificates rsync inotify-tools python3 git \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/supervisor /run/nginx \
    && chown -R www-data:www-data /var/log/nginx /run/nginx

COPY --from=oven/bun:1-slim /usr/local/bin/bun /usr/local/bin/bun
COPY --from=oven/bun:1-slim /usr/local/bin/bunx /usr/local/bin/bunx

COPY --from=sillytavern /home/node/app /apps/sillytavern
COPY --from=marinara /app /apps/marinara
COPY --from=marinara /usr/local/bin/marinara-docker-entrypoint.mjs /usr/local/bin/marinara-docker-entrypoint.mjs
COPY --from=lumiverse-build /build /apps/lumiverse

COPY docker/ /opt/hub/docker/
COPY scripts/ /opt/hub/scripts/
COPY config/ /opt/hub/config/
COPY public/ /opt/hub/public/

RUN chmod +x /opt/hub/docker/*.sh /opt/hub/scripts/*.sh \
    && mkdir -p /data \
    && chown -R node:node /apps/sillytavern /apps/marinara /data

ENV DATA_ROOT=/data
ENV HUB_PORT=7860
ENV ACTIVE_APP=sillytavern
ENV ST_PORT=8000
ENV LUMIVERSE_PORT=7861
ENV MARINARA_PORT=7862

VOLUME ["/data"]
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:7870/api/health" || exit 1

ENTRYPOINT ["/opt/hub/docker/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/opt/hub/docker/supervisord.conf"]