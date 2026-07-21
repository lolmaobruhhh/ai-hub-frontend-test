---
title: Lumiverse
emoji: 🌌
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Lumiverse on Hugging Face

Deploy **[Lumiverse](https://github.com/prolix-oc/Lumiverse)** — a modern AI roleplay chat
frontend — on a single [Hugging Face Space](https://huggingface.co/spaces) (free-tier friendly),
with persistent storage under `/data` and a built-in **Character Discovery** dashboard for
browsing and one-click importing cards from Chub.ai and Wyvernchat.

| | |
|---|---|
| **Frontend** | Lumiverse (`ghcr.io/prolix-oc/lumiverse:latest`, prebuilt image) |
| **Port** | one port `7860` (HF requirement) |
| **Storage** | persistent bucket mounted at `/data` → SQLite DB + uploads |
| **Discovery** | `/discover` — browse & import from Chub + Wyvern |

## Architecture

A tiny Python gateway on `:7860` fronts Lumiverse (running internally on `:7861`) and serves
the discovery dashboard on the **same origin**, so your Lumiverse login cookie flows straight
into imports — no tokens to manage.

```
HF Space :7860  ── hub-gateway.py ──┬─ /discover           → character-import dashboard
                                     ├─ /hub-proxy/chub/*   → api.chub.ai   (server-side)
                                     ├─ /hub-proxy/wyvern/* → api.wyvern.chat
                                     ├─ WebSocket           → Lumiverse :7861 (raw tunnel)
                                     └─ everything else     → Lumiverse :7861 (streaming)
```

The gateway does **no HTML/JS rewriting** — Lumiverse is served transparently at the root path,
and responses (including SSE chat streams and websockets) are proxied byte-for-byte.

## Deploy

### Option A — Import from GitHub (recommended)

1. [huggingface.co/new-space](https://huggingface.co/new-space) → **Docker** SDK
2. **Import from GitHub** → this repo (branch `lumiverse`)
3. Create Space → wait for the build

### Option B — Paste Dockerfile only

The Dockerfile clones its hub scripts from GitHub at build time. You only need **two files** in
the Space: `Dockerfile` and `README.md` (with the `---` yaml frontmatter above — HF needs
`sdk: docker` and `app_port: 7860`).

### After create

1. **Settings → Persistent storage** → mount a bucket at **`/data`** (Lumiverse writes
   `/data/lumiverse/lumiverse.db` + uploaded images there; without it, data resets on restart).
2. **Settings → Secrets** (optional):
   - `PUBLIC_ORIGIN` — `https://your-space.hf.space` (auto-detected from `SPACE_HOST` /
     `SPACE_ID` when omitted; needed for BetterAuth login).
   - `OWNER_PASSWORD` — Lumiverse first-time owner setup, if you use it.
3. Open the Space URL → sign in to Lumiverse → visit **`/discover`** to browse characters.

## Character Discovery (`/discover`)

Lumiverse natively imports a character only from a **single pasted URL** (Chub, JannyAI,
BotBooru, or a direct PNG/JSON link) and has no browse UI. The `/discover` dashboard adds that:

- **Sources:** Chub.ai and Wyvernchat (DataCat / Pygmalion tabs are stubbed for future work).
- **Chub:** full-text search, include/exclude **tags**, sort by downloads / trending / stars /
  favorites / rating / newest / name (asc/desc), NSFW toggle.
- **Wyvern:** popular / newest / curator-picks feeds, search, NSFW (`mature`) feeds.
- Responsive card grid with thumbnails, tags, creator, and stats; infinite scroll.
- **One-click Import** into Lumiverse:
  - Chub → uses Lumiverse's native `POST /api/v1/characters/import-url`.
  - Wyvern → converts the card to Tavern **V2** JSON and uploads via
    `POST /api/v1/characters/import`.

You must be **logged into Lumiverse** (same browser) for imports — the import call reuses your
session cookie. If you see "Log in first", open the main app and sign in.

> Chub sits behind Cloudflare; from some datacenter IPs its API may be rate-limited or
> challenged. The dashboard surfaces a friendly error rather than failing silently.

## Local test

```bash
docker build -t lumiverse-hf .
docker run --rm -it -p 7860:7860 \
  -e PUBLIC_ORIGIN=http://localhost:7860 \
  -v "$(pwd)/_data:/data" \
  lumiverse-hf
```

- App: <http://localhost:7860/>
- Discovery: <http://localhost:7860/discover>
- Proxy check: `curl 'http://localhost:7860/hub-proxy/chub/search?namespace=characters&first=5&sort=download_count'`

## Notes / limitations

- **First boot** takes a bit while Lumiverse starts (the gateway waits up to ~180s for `:7861`;
  early requests may briefly 502).
- **Free-tier sleep** — the Space sleeps after idle; `/data` persists via the storage bucket.
- Runs as **uid 1000** (`node` user); `/data` must be writable (handled at boot).

## License

Hub gateway + dashboard scripts: MIT. Lumiverse retains its own license (see the
[Lumiverse repo](https://github.com/prolix-oc/Lumiverse)).
