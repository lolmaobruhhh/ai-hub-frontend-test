#!/usr/bin/env python3
"""Hub launcher API — only /hub and /api/switch|health|active."""
from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DATA_ROOT = os.environ.get("DATA_ROOT", "/data")
PUBLIC = Path("/opt/hub/public")
SWITCH_SCRIPT = "/opt/hub/docker/switch-app.sh"
PORT = int(os.environ.get("HUB_API_PORT", "7870"))


def active_app() -> str:
    path = os.path.join(DATA_ROOT, ".active_app")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or "sillytavern"
    return "sillytavern"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[hub-api] {self.address_string()} - {fmt % args}", flush=True)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, filename: str) -> None:
        path = PUBLIC / filename
        if not path.is_file():
            self._json(404, {"error": "hub page missing"})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in {"/hub", "/hub/", "/api/hub", "/api/hub/"}:
            self._html("index.html")
            return

        if path == "/api/health":
            self._json(200, {"status": "ok", "active": active_app()})
            return

        if path == "/api/active":
            self._json(200, {"active": active_app()})
            return

        if path.startswith("/api/switch/"):
            app = path.rsplit("/", 1)[-1].lower()
            if app not in {"sillytavern", "lumiverse", "marinara"}:
                self._json(400, {"error": "unknown app"})
                return
            try:
                subprocess.run([SWITCH_SCRIPT, app], check=True, timeout=120)
            except subprocess.CalledProcessError as exc:
                self._json(500, {"error": "switch failed", "detail": str(exc)})
                return
            except subprocess.TimeoutExpired:
                self._json(504, {"error": "switch timed out"})
                return
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        self._json(404, {"error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[hub-api] listening on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()