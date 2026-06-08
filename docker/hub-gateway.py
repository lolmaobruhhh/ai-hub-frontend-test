#!/usr/bin/env python3
"""HF public gateway on :7860 — dynamic routing via .active_app (no nginx reload)."""
from __future__ import annotations

import http.client
import json
import os
import select
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
PUBLIC = Path("/opt/hub/public")
SWITCH_SCRIPT = "/opt/hub/docker/switch-app.sh"
ACTIVE_FILE = DATA_ROOT / ".active_app"
HUB_PORT = int(os.environ.get("HUB_PORT", "7860"))

PORTS = {
    "sillytavern": int(os.environ.get("ST_PORT", "8000")),
    "lumiverse": int(os.environ.get("LUMIVERSE_PORT", "7861")),
    "marinara": int(os.environ.get("MARINARA_PORT", "7862")),
}

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

SKIP_REQUEST_HEADERS = {"host", "connection", "content-length", "transfer-encoding"}


def active_app() -> str:
    if ACTIVE_FILE.is_file():
        name = ACTIVE_FILE.read_text(encoding="utf-8").strip().lower()
        if name in PORTS:
            return name
    return "sillytavern"


def backend_port(app: str | None = None) -> int:
    return PORTS.get(app or active_app(), PORTS["sillytavern"])


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def backend_ready(app: str | None = None) -> bool:
    app = app or active_app()
    port = PORTS.get(app)
    if port is None or not port_open(port):
        return False
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/", headers={"Accept": "text/html,application/json", "User-Agent": "hub-ready-probe"})
        resp = conn.getresponse()
        resp.read()
        return 200 <= resp.status < 500
    except Exception:
        return port_open(port)


def is_hub_api_path(path: str) -> bool:
    if path in {"/api/hub", "/api/hub/", "/api/health", "/api/active", "/api/ready", "/api/debug", "/api/sync"}:
        return True
    return path.startswith("/api/switch/")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "hub-gateway/2"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[gateway] {self.address_string()} - {fmt % args}", flush=True)

    def _send_bytes(self, code: int, body: bytes, content_type: str, extra_headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict) -> None:
        self._send_bytes(code, json.dumps(payload).encode("utf-8"), "application/json")

    def _send_html(self, filename: str, cache_control: str = "no-cache") -> None:
        path = PUBLIC / filename
        if not path.is_file():
            self._send_json(404, {"error": f"{filename} missing"})
            return
        self._send_bytes(
            200,
            path.read_bytes(),
            "text/html; charset=utf-8",
            {"Cache-Control": cache_control},
        )

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _run_switch(self, app: str) -> tuple[int, list[str]]:
        try:
            proc = subprocess.run(
                [SWITCH_SCRIPT, app],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            out = (proc.stdout or proc.stderr or "").strip().splitlines()
            tail = out[-5:] if out else []
            if proc.returncode != 0:
                print(f"[gateway] switch to {app} exit {proc.returncode}: {tail}", flush=True)
            else:
                print(f"[gateway] switch to {app} ok — active={active_app()}: {tail}", flush=True)
            return proc.returncode, tail
        except Exception as exc:
            print(f"[gateway] switch to {app} failed: {exc}", flush=True)
            return 1, [str(exc)]

    def _handle_hub_route(self, method: str) -> bool:
        path = urlparse(self.path).path

        if path in {"/api/hub", "/api/hub/", "/hub/", "/hub.html"}:
            filename = "hub.html" if path == "/hub.html" else "index.html"
            self._send_html(filename)
            return True

        if path == "/hub":
            self._send_html("hub-redirect.html")
            return True

        if path in {"/sillytavern", "/sillytavern/", "/lumiverse", "/lumiverse/", "/marinara", "/marinara/"}:
            app = path.strip("/").lower()
            self._redirect(f"/api/switch/{app}")
            return True

        if path == "/api/health":
            self._send_json(200, {"status": "ok", "active": active_app(), "backend_port": backend_port()})
            return True

        if path == "/api/active":
            self._send_json(200, {"active": active_app(), "backend_port": backend_port()})
            return True

        if path == "/api/ready":
            app = active_app()
            self._send_json(200, {"active": app, "ready": backend_ready(app), "backend_port": backend_port(app)})
            return True

        if path == "/api/debug":
            probes = {}
            for name, port in PORTS.items():
                probes[name] = {
                    "port": port,
                    "port_open": port_open(port),
                    "http_ready": backend_ready(name),
                }
            self._send_json(
                200,
                {
                    "active": active_app(),
                    "backend_port": backend_port(),
                    "active_ready": backend_ready(),
                    "gateway": f"0.0.0.0:{HUB_PORT}",
                    "routing": "dynamic (.active_app per request)",
                    "backends": probes,
                },
            )
            return True

        if path == "/api/sync" and method == "GET":
            try:
                proc = subprocess.run(
                    ["/opt/hub/scripts/sync-shared-data.sh"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                lines = (proc.stdout or proc.stderr or "").strip().splitlines()
                tail = lines[-8:] if lines else []
                self._send_json(
                    200,
                    {"ok": proc.returncode == 0, "exit_code": proc.returncode, "log": tail},
                )
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return True

        if path.startswith("/api/switch/") and method == "GET":
            app = path.rsplit("/", 1)[-1].lower()
            if app not in PORTS:
                self._send_json(400, {"error": "unknown app"})
                return True
            self._run_switch(app)
            self._send_html("switching.html")
            return True

        return False

    def _build_forward_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in SKIP_REQUEST_HEADERS:
                continue
            headers[key] = value
        host = self.headers.get("Host", "")
        if host:
            headers["X-Forwarded-Host"] = host
        headers["X-Forwarded-Proto"] = os.environ.get("FORWARDED_PROTO", "https")
        headers["X-Real-IP"] = self.client_address[0]
        prior = self.headers.get("X-Forwarded-For", "")
        client_ip = self.client_address[0]
        headers["X-Forwarded-For"] = f"{prior}, {client_ip}" if prior else client_ip
        return headers

    def _proxy_http(self, method: str) -> None:
        port = backend_port()
        parsed = urlparse(self.path)
        target_path = parsed.path or "/"
        if parsed.query:
            target_path = f"{target_path}?{parsed.query}"

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3600)
        try:
            conn.request(method, target_path, body=body, headers=self._build_forward_headers())
            resp = conn.getresponse()
            self.send_response(resp.status)
            for key, value in resp.getheaders():
                if key.lower() in HOP_BY_HOP:
                    continue
                self.send_header(key, value)
            data = resp.read()
            if "Content-Length" not in {k for k, _ in resp.getheaders()}:
                self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            print(f"[gateway] proxy {method} → :{port}{target_path} failed: {exc}", flush=True)
            self._send_json(502, {"error": "backend unavailable", "active": active_app(), "port": port})
        finally:
            conn.close()

    def _proxy_websocket(self) -> None:
        port = backend_port()
        parsed = urlparse(self.path)
        target_path = parsed.path or "/"
        if parsed.query:
            target_path = f"{target_path}?{parsed.query}"

        lines = [f"{self.command} {target_path} {self.request_version}"]
        for key, value in self.headers.items():
            lower = key.lower()
            if lower == "host":
                value = f"127.0.0.1:{port}"
            lines.append(f"{key}: {value}")
        lines.append("")
        lines.append("")
        payload = "\r\n".join(lines).encode("latin-1", errors="replace")

        client = self.connection
        backend = socket.create_connection(("127.0.0.1", port), timeout=60)
        try:
            backend.sendall(payload)
            sockets = [client, backend]
            while True:
                readable, _, _ = select.select(sockets, [], [], 3600)
                if not readable:
                    break
                for sock in readable:
                    chunk = sock.recv(65536)
                    if not chunk:
                        return
                    other = backend if sock is client else client
                    other.sendall(chunk)
        except Exception as exc:
            print(f"[gateway] websocket → :{port}{target_path} failed: {exc}", flush=True)
        finally:
            backend.close()

    def handle(self) -> None:
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                return
            if not self.parse_request():
                return

            if self._handle_hub_route(self.command):
                return

            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._proxy_websocket()
                return

            mname = f"do_{self.command}"
            if not hasattr(self, mname):
                self.send_error(501, "Unsupported method")
                return
            getattr(self, mname)()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self) -> None:
        self._proxy_http("GET")

    def do_HEAD(self) -> None:
        self._proxy_http("HEAD")

    def do_POST(self) -> None:
        self._proxy_http("POST")

    def do_PUT(self) -> None:
        self._proxy_http("PUT")

    def do_PATCH(self) -> None:
        self._proxy_http("PATCH")

    def do_DELETE(self) -> None:
        self._proxy_http("DELETE")

    def do_OPTIONS(self) -> None:
        self._proxy_http("OPTIONS")


def main() -> None:
    app = active_app()
    print(
        f"[gateway] starting on 0.0.0.0:{HUB_PORT} active={app} backend=:{backend_port(app)}",
        flush=True,
    )
    server = ThreadingHTTPServer(("0.0.0.0", HUB_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()