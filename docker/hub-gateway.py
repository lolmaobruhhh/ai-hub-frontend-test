#!/usr/bin/env python3
"""Slim HF gateway on :7860.

Serves Lumiverse (127.0.0.1:7861) transparently at / — NO body rewriting, since
Lumiverse now runs at the root path (no subpath). Additionally serves:

  GET  /discover[/]              → public/discover.html (character-import dashboard)
  GET  /hub-proxy/chub/search    → server-side proxy to api.chub.ai/search
  GET  /hub-proxy/chub/card      → server-side proxy to the Chub card PNG
  GET  /hub-proxy/wyvern/list    → server-side proxy to api.wyvern.chat feeds
  GET  /hub-proxy/wyvern/card    → server-side proxy to a single Wyvern character

Everything else (including /api/v1/*, websockets, SSE chat streams) is proxied to
Lumiverse. Same-origin means the browser's Lumiverse session cookie flows straight
through, so one-click character import works without any token handling.
"""
from __future__ import annotations

import json
import os
import select
import socket
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PUBLIC = Path("/opt/hub/public")
HUB_PORT = int(os.environ.get("HUB_PORT", "7860"))
LUMIVERSE_PORT = int(os.environ.get("LUMIVERSE_PORT", "7861"))
LUMI_HOST = "127.0.0.1"

# A realistic browser UA — api.chub.ai sits behind Cloudflare and rejects bare
# python-urllib. api.wyvern.chat is friendlier but we send it too for consistency.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CHUB_SEARCH = "https://api.chub.ai/search"
CHUB_CARD = "https://avatars.charhub.io/avatars/{fullPath}/chara_card_v2.png"
WYVERN_BASE = "https://api.wyvern.chat"

# Whitelisted Chub search params (everything else is dropped before forwarding).
CHUB_PARAMS = {
    "search", "namespace", "first", "page", "sort", "asc",
    "topics", "excludetopics", "nsfw", "nsfw_only", "include_forks",
    "require_images", "require_custom_prompt", "min_tokens", "max_tokens",
    "inclusive_or", "venus",
}

# Wyvern feeds we allow (feed name → path on api.wyvern.chat).
WYVERN_FEEDS = {
    "public": "/characters/public",
    "public/mature": "/characters/public/mature",
    "popular": "/characters/popular",
    "popular/mature": "/characters/popular/mature",
    "curator-picks": "/characters/curator-picks/homepage",
}

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}

# Request headers we never forward upstream to Lumiverse.
SKIP_REQUEST_HEADERS = {"connection", "keep-alive", "proxy-connection", "te", "upgrade"}

STREAM_CHUNK = 65536


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "lumiverse-gateway/1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[gateway] {self.address_string()} - {fmt % args}", flush=True)

    # ── small response helpers ──────────────────────────────────────────────
    def _send_bytes(self, code: int, body: bytes, content_type: str,
                    extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, code: int, payload: dict) -> None:
        self._send_bytes(code, json.dumps(payload).encode("utf-8"), "application/json")

    def _send_html(self, filename: str) -> None:
        path = PUBLIC / filename
        if not path.is_file():
            self._send_json(404, {"error": f"{filename} missing"})
            return
        self._send_bytes(200, path.read_bytes(), "text/html; charset=utf-8",
                         {"Cache-Control": "no-cache"})

    # ── external fetch helper (Chub / Wyvern) ───────────────────────────────
    def _proxy_external(self, url: str, *, as_json: bool, content_type: str | None = None) -> None:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": BROWSER_UA,
                     "Accept": "application/json" if as_json else "*/*"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                ct = content_type or resp.headers.get("Content-Type") or (
                    "application/json" if as_json else "application/octet-stream")
        except urllib.error.HTTPError as exc:
            body = exc.read()[:2000].decode("utf-8", "replace")
            self._send_json(exc.code if 400 <= exc.code < 600 else 502, {
                "error": f"upstream {exc.code}",
                "detail": body[:500],
                "hint": "Chub sits behind Cloudflare; a datacenter IP may be challenged.",
            })
            return
        except Exception as exc:  # noqa: BLE001
            self._send_json(502, {"error": "upstream fetch failed", "detail": str(exc)})
            return
        self._send_bytes(200, data, ct, {"Cache-Control": "no-store"})

    def _handle_hub_proxy(self, path: str, query: str) -> bool:
        if path == "/discover" or path == "/discover/":
            self._send_html("discover.html")
            return True

        if path == "/browse" or path == "/browse/":
            self.send_response(302)
            self.send_header("Location", "/discover")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            return True

        if path == "/hub-proxy/chub/search":
            params = urllib.parse.parse_qsl(query, keep_blank_values=True)
            kept = [(k, v) for k, v in params if k in CHUB_PARAMS]
            url = CHUB_SEARCH + ("?" + urllib.parse.urlencode(kept) if kept else "")
            self._proxy_external(url, as_json=True)
            return True

        if path == "/hub-proxy/chub/card":
            qs = dict(urllib.parse.parse_qsl(query))
            full = (qs.get("fullPath") or "").strip().strip("/")
            if not full or ".." in full:
                self._send_json(400, {"error": "fullPath required"})
                return True
            self._proxy_external(CHUB_CARD.format(fullPath=full),
                                 as_json=False, content_type="image/png")
            return True

        if path == "/hub-proxy/wyvern/list":
            qs = dict(urllib.parse.parse_qsl(query, keep_blank_values=True))
            feed = qs.get("feed", "public")
            feed_path = WYVERN_FEEDS.get(feed)
            if not feed_path:
                self._send_json(400, {"error": "unknown feed", "feeds": sorted(WYVERN_FEEDS)})
                return True
            passthru = [(k, v) for k, v in qs.items() if k in ("query", "page", "limit", "tags", "sort", "sortBy")]
            url = WYVERN_BASE + feed_path + ("?" + urllib.parse.urlencode(passthru) if passthru else "")
            self._proxy_external(url, as_json=True)
            return True

        if path == "/hub-proxy/wyvern/card":
            qs = dict(urllib.parse.parse_qsl(query))
            cid = (qs.get("id") or "").strip()
            if not cid or "/" in cid:
                self._send_json(400, {"error": "id required"})
                return True
            self._proxy_external(f"{WYVERN_BASE}/characters/{urllib.parse.quote(cid)}", as_json=True)
            return True

        return False

    # ── transparent streaming passthrough to Lumiverse ──────────────────────
    def _proxy_to_lumiverse(self, method: str) -> None:
        parsed = urlparse(self.path)
        backend_path = parsed.path
        if parsed.query:
            backend_path += "?" + parsed.query

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        # Forward client headers mostly untouched; only rewrite Host and drop
        # hop-by-hop. Do NOT strip Accept-Encoding — we never rewrite the body,
        # so compressed responses pass through opaquely.
        fwd_headers = []
        for key, value in self.headers.items():
            if key.lower() in SKIP_REQUEST_HEADERS or key.lower() == "host":
                continue
            fwd_headers.append((key, value))
        fwd_headers.append(("Host", f"{LUMI_HOST}:{LUMIVERSE_PORT}"))
        fwd_headers.append(("X-Forwarded-Proto", os.environ.get("FORWARDED_PROTO", "https")))
        fwd_headers.append(("X-Real-IP", self.client_address[0]))
        prior = self.headers.get("X-Forwarded-For", "")
        fwd_headers.append(
            ("X-Forwarded-For", f"{prior}, {self.client_address[0]}" if prior else self.client_address[0]))
        host = self.headers.get("Host", "")
        if host:
            fwd_headers.append(("X-Forwarded-Host", host))

        try:
            backend = socket.create_connection((LUMI_HOST, LUMIVERSE_PORT), timeout=3600)
        except OSError as exc:
            self._send_json(502, {"error": "lumiverse unavailable", "detail": str(exc)})
            return

        try:
            # Build and send the raw request line + headers ourselves so we can
            # stream the response byte-for-byte (http.client would decode chunked
            # transfer-encoding and defeat SSE). We use HTTP/1.0 upstream + read
            # until EOF, which is the simplest correct way to stream any body
            # (SSE, chunked, or fixed-length) without buffering.
            #
            # ⚠️  STREAMING GUARD: do NOT replace this with resp.read() + a fixed
            #     Content-Length. Lumiverse chat generation is text/event-stream;
            #     buffering makes chat "hang then dump" and can hang forever on
            #     open streams. Stream chunk-by-chunk with flush().
            req_lines = [f"{method} {backend_path} HTTP/1.0\r\n"]
            for key, value in fwd_headers:
                req_lines.append(f"{key}: {value}\r\n")
            req_lines.append("Connection: close\r\n")
            if body is not None:
                req_lines.append(f"Content-Length: {len(body)}\r\n")
            req_lines.append("\r\n")
            backend.sendall("".join(req_lines).encode("latin-1", "replace"))
            if body:
                backend.sendall(body)

            # Relay the upstream response VERBATIM (status line + headers + body)
            # to the client. We forced Connection: close upstream, so the backend
            # closes at end-of-body and our read loop terminates naturally —
            # correct for SSE, chunked, and fixed-length alike. We write nothing
            # to self.wfile before this: _pump_raw takes over the raw socket, so
            # the backend's own valid HTTP response reaches the client unchanged.
            self._pump_raw(backend)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            print(f"[gateway] proxy {method} {backend_path} failed: {exc}", flush=True)
        finally:
            try:
                backend.close()
            except OSError:
                pass

    def _pump_raw(self, backend: socket.socket) -> None:
        """Copy the raw upstream HTTP response (status line + headers + body)
        straight to the client socket, flushing each chunk. We bypass
        BaseHTTPRequestHandler's response machinery and write directly to the
        connection so the backend's response framing is preserved byte-for-byte
        (essential for SSE / streaming)."""
        conn = self.connection
        while True:
            try:
                chunk = backend.recv(STREAM_CHUNK)
            except OSError:
                break
            if not chunk:
                break
            try:
                conn.sendall(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                break

    # ── websocket tunnel (raw socket bridge) ────────────────────────────────
    def _proxy_websocket(self) -> None:
        parsed = urlparse(self.path)
        backend_path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        lines = [f"{self.command} {backend_path} {self.request_version}"]
        for key, value in self.headers.items():
            if key.lower() == "host":
                value = f"{LUMI_HOST}:{LUMIVERSE_PORT}"
            lines.append(f"{key}: {value}")
        lines.extend(["", ""])
        payload = "\r\n".join(lines).encode("latin-1", errors="replace")

        client = self.connection
        try:
            backend = socket.create_connection((LUMI_HOST, LUMIVERSE_PORT), timeout=60)
        except OSError as exc:
            print(f"[gateway] websocket connect failed: {exc}", flush=True)
            return
        try:
            backend.sendall(payload)
            socks = [client, backend]
            while True:
                readable, _, _ = select.select(socks, [], [], 3600)
                if not readable:
                    break
                for sock in readable:
                    chunk = sock.recv(STREAM_CHUNK)
                    if not chunk:
                        return
                    (backend if sock is client else client).sendall(chunk)
        except Exception as exc:  # noqa: BLE001
            print(f"[gateway] websocket bridge failed: {exc}", flush=True)
        finally:
            backend.close()

    # ── dispatch ────────────────────────────────────────────────────────────
    def handle_one_request(self) -> None:  # type: ignore[override]
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                return

            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._proxy_websocket()
                self.close_connection = True
                return

            parsed = urlparse(self.path)
            if self.command == "GET" and self._handle_hub_proxy(parsed.path, parsed.query):
                self.close_connection = True
                return

            self._proxy_to_lumiverse(self.command)
            self.close_connection = True
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True


def main() -> None:
    print(f"[gateway] starting on 0.0.0.0:{HUB_PORT} → lumiverse 127.0.0.1:{LUMIVERSE_PORT} "
          f"(discover=/discover, hub-proxy=/hub-proxy/*)", flush=True)
    ThreadingHTTPServer.request_queue_size = 512
    server = ThreadingHTTPServer(("0.0.0.0", HUB_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
