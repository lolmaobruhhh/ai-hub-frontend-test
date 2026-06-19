# =============================================================================
# AI Frontends Hub — Hugging Face Space (UID 1000 / node user, lightweight)
# Repo: https://github.com/lolmaobruhhh/ai-hub-frontend-test
# =============================================================================

FROM alpine:3.20 AS hub-src
RUN apk add --no-cache git \
    && git clone --depth 1 https://github.com/lolmaobruhhh/ai-hub-frontend-test.git /hub

# Upstream images pinned to digests for reproducible builds. Floating tags
# (:latest / :lite) silently pulled a newer build on every rebuild — that is how
# Lumiverse jumped versions (migrations 074-087) and can introduce regressions
# like generate-request validation changes. Bump these deliberately, not by luck.
# Lumiverse only ships staging-*/latest (no stable channel), so digest-pinning is
# the ONLY way to freeze it. Never pin Lumiverse OLDER than the migrated /data DB.
#   sillytavern : 1.18.0
#   marinara    : latest (full engine — sidecar local model + embeddings + memory recall)
#   lumiverse   : latest @ 2026-06-19 working build (migrations through 087)
FROM ghcr.io/sillytavern/sillytavern@sha256:7027bdf302ba8f60705db0118286195c9ab30c9271d1a52f7786d8d6fa235577 AS sillytavern
FROM ghcr.io/pasta-devs/marinara-engine@sha256:fe2ae72007c7d4653cc3a55e2e2f2c642f7bd09361b02e4805940dece279a7e0 AS marinara
FROM ghcr.io/prolix-oc/lumiverse@sha256:637023307ff848f0c60ef468d438739cc1bdc28d286042f645ee00113233c9a3 AS lumiverse

FROM node:24-bookworm-slim

# node:24-bookworm-slim already has `node` at UID 1000 (HF requirement)
RUN apt-get update && apt-get install -y --no-install-recommends \
      nginx python3 curl ca-certificates rsync git \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp && chmod 777 /tmp

COPY --from=lumiverse /usr/local/bin/bun /usr/local/bin/bun
COPY --from=hub-src --chown=node:node /hub/docker /opt/hub/docker/
COPY --from=hub-src --chown=node:node /hub/scripts /opt/hub/scripts/
COPY --from=hub-src --chown=node:node /hub/config /opt/hub/config/
COPY --from=hub-src --chown=node:node /hub/public /opt/hub/public/
RUN cp /opt/hub/public/index.html /opt/hub/public/hub.html
COPY --from=sillytavern --chown=node:node /home/node/app /apps/sillytavern
COPY --from=marinara --chown=node:node /app /apps/marinara
COPY --from=lumiverse --chown=node:node /app /apps/lumiverse

RUN chmod +x /opt/hub/docker/*.sh /opt/hub/scripts/*.sh \
    && chmod +x /opt/hub/docker/start-all-apps.sh \
    && echo 'upstream active_backend { server 127.0.0.1:8000; }' > /opt/hub/docker/upstream.conf \
    && /opt/hub/docker/patch-lumiverse-auth.sh \
    && /opt/hub/docker/patch-app-subpaths.sh \
    && /opt/hub/docker/patch-lumiverse-sw.sh \
    && /opt/hub/docker/patch-marinara-sw.sh


USER node
ENV HOME=/home/node
WORKDIR /home/node

ENV DATA_ROOT=/data
ENV HUB_PORT=7860
ENV ACTIVE_APP=sillytavern
ENV ST_PORT=8000
ENV LUMIVERSE_PORT=7861
ENV MARINARA_PORT=7862
ENV NODE_ENV=production
ENV TRUST_ANY_ORIGIN=true
ENV FORWARDED_PROTO=https

# Global Space Protection Password (Basic Auth user: admin)
ENV GLOBAL_PASSWORD=admin
# Lumiverse Owner Password
ENV OWNER_PASSWORD=admin123

EXPOSE 7860

CMD ["bash", "/opt/hub/docker/start-hf.sh"]
