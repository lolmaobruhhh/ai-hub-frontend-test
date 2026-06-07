#!/usr/bin/env python3
"""HF-compatible gateway on :7860 — no nginx/root required."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
PUBLIC = Path("/opt/hub/public")
SWITCH_SCRIPT = "/opt/hub/docker/switch-app.sh"
ACTIVE_FILE = DATA_ROOT / ".active_app"
BACKEND_FILE = Path("/opt/hub/docker/upstream.conf")

PORTS = {
    "sillytavern": int(os.environ.get("ST_PORT", "8000")),
    "lumiverse": int(os.environ.get("LUMIVERSE_PORT", "7861")),
    "marinara": int(os.environ.get("MARINARA_PORT", "7862")),
}


def active_app() -> str:
    if ACTIVE_FILE.is_file():
        return ACTIVE_FILE.read_text(encoding="utf-8").strip() or "sillytavern"
    return "sillytavern"


def backend_port() -> int:
    return PORTS.get(active_app(), PORTS["sillytavern"])


def proxy_request(method: str, path: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    port = backend_port()
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        if k.lower() in {"host", "connection", "content-length"}:
            continue
        req.add_header(k, v)
    req.add_header("X-Forwarded-Proto", os.environ.get("FORWARDED_PROTO", "https"))
    req.add_header("X-Forwarded-Host", headers.get("Host", ""))
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[gateway] {self.address_string()} {fmt % args}", flush=True)

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, filename: str) -> bool:
        path = PUBLIC / filename
        if not path.is_file():
            return False
        data = path.read_bytes()
        ctype = "text/html" if filename.endswith(".html") else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/hub", "/hub/"}:
            self._serve_static("index.html")
            return
        if path == "/api/health":
            self._send_json(200, {"status": "ok", "active": active_app(), "backend_port": backend_port()})
            return
        if path == "/api/active":
            self._send_json(200, {"active": active_app(), "backend_port": backend_port()})
            return
        if path.startswith("/api/switch/"):
            app = path.rsplit("/", 1)[-1].lower()
            if app not in PORTS:
                self._send_json(400, {"error": "unknown app"})
                return
            subprocess.run([SWITCH_SCRIPT, app], check=False)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        status, hdrs, body = proxy_request("GET", self.path, dict(self.headers), None)
        self.send_response(status)
        for k, v in hdrs.items():
            if k.lower() not in {"transfer-encoding", "connection"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        status, hdrs, resp = proxy_request("POST", self.path, dict(self.headers), body)
        self.send_response(status)
        for k, v in hdrs.items():
            if k.lower() not in {"transfer-encoding", "connection"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_PUT(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        status, hdrs, resp = proxy_request("PUT", self.path, dict(self.headers), body)
        self.send_response(status)
        for k, v in hdrs.items():
            if k.lower() not in {"transfer-encoding", "connection"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_DELETE(self) -> None:
        status, hdrs, resp = proxy_request("DELETE", self.path, dict(self.headers), None)
        self.send_response(status)
        for k, v in hdrs.items():
            if k.lower() not in {"transfer-encoding", "connection"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def main() -> None:
    port = int(os.environ.get("HUB_PORT", "7860"))
    print(f"[gateway] starting on 0.0.0.0:{port} active={active_app()}", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()