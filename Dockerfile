# =============================================================================
# Lumiverse on Hugging Face Space (UID 1000 / node user, lightweight)
# Single frontend (Lumiverse) served at / on port 7860 by a slim Python gateway
# that also serves the /discover character-import dashboard.
# Repo: https://github.com/lolmaobruhhh/ai-hub-frontend-test  (branch: lumiverse)
# =============================================================================

FROM alpine:3.20 AS hub-src
RUN apk add --no-cache git \
    && git clone --depth 1 --branch lumiverse https://github.com/lolmaobruhhh/ai-hub-frontend-test.git /hub

FROM ghcr.io/prolix-oc/lumiverse:latest AS lumiverse

FROM node:24-bookworm-slim

# node:24-bookworm-slim already has `node` at UID 1000 (HF requirement)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp && chmod 777 /tmp

COPY --from=lumiverse /usr/local/bin/bun /usr/local/bin/bun
COPY --from=hub-src --chown=node:node /hub/docker /opt/hub/docker/
COPY --from=hub-src --chown=node:node /hub/scripts /opt/hub/scripts/
COPY --from=hub-src --chown=node:node /hub/public /opt/hub/public/
COPY --from=lumiverse --chown=node:node /app /apps/lumiverse

RUN chmod +x /opt/hub/docker/*.sh /opt/hub/scripts/*.sh


USER node
ENV HOME=/home/node
WORKDIR /home/node

ENV DATA_ROOT=/data
ENV HUB_PORT=7860
ENV LUMIVERSE_PORT=7861
ENV NODE_ENV=production
ENV TRUST_ANY_ORIGIN=true
ENV FORWARDED_PROTO=https

EXPOSE 7860

CMD ["bash", "/opt/hub/docker/start-hf.sh"]
