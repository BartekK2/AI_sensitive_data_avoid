"""HTTP forward proxy for apps that honor HTTP_PROXY / HTTPS_PROXY.

Plain HTTP bodies are scanned. HTTPS CONNECT is tunneled, except for a short
list of AI hosts where we do company-consented TLS inspection (local Helios CA).
"""

from __future__ import annotations

import json
import select
import socket
import ssl
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .tlsmitm import (
    client_ssl_context,
    relay_http11,
    should_intercept,
)

TRAFFIC_LOG = Path(__file__).resolve().parents[1] / "data" / "proxy_traffic.jsonl"
PINNED_HOSTS: set[str] = set()

DEFAULT_AI_HOSTS = {
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.groq.com",
    "api.mistral.ai",
    "api.deepseek.com",
    "openrouter.ai",
    "api.x.ai",
}


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        try:
            print("[proxy]", fmt % args)
        except UnicodeEncodeError:
            print("[proxy]", (fmt % args).encode("ascii", "replace").decode("ascii"))

    def do_CONNECT(self) -> None:
        host_port = self.path
        host = host_port.split(":")[0].lower()
        log_traffic("CONNECT", host, self.path)
        if not self.server.allow_host(host):
            self.send_error(403, f"destination blocked by policy: {host}")
            return
        try:
            port = int(host_port.split(":")[1]) if ":" in host_port else 443
        except ValueError:
            port = 443
        intercept = (
            self.server.mitm
            and should_intercept(host)
            and host not in PINNED_HOSTS
        )
        if intercept:
            self._mitm_connect(host, port)
            return
        try:
            upstream = socket.create_connection((host, port), timeout=20)
        except OSError as error:
            self.send_error(502, str(error))
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        _tunnel(self.connection, upstream)

    def _mitm_connect(self, host: str, port: int) -> None:
        from .tlsca import issue_host_cert

        self.close_connection = True
        try:
            cert_path, key_path = issue_host_cert(host)
        except OSError as error:
            self.send_error(502, str(error))
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        try:
            client = client_ssl_context(cert_path, key_path).wrap_socket(
                self.connection, server_side=True
            )
        except ssl.SSLError as error:
            print("[proxy] MITM handshake failed (zainstaluj CA albo host pinuje):", host, error)
            return
        try:
            relay_http11(client, host, self.server.inspect, log=log_traffic)
        except OSError as error:
            print("[proxy] MITM relay", host, error)
        finally:
            try:
                client.close()
            except OSError:
                pass

    def do_GET(self) -> None:
        self._proxy_http()

    def do_POST(self) -> None:
        self._proxy_http()

    def do_PUT(self) -> None:
        self._proxy_http()

    def do_PATCH(self) -> None:
        self._proxy_http()

    def do_DELETE(self) -> None:
        self._proxy_http()

    def _proxy_http(self) -> None:
        parsed = urlparse(self.path)
        host = (parsed.hostname or "").lower()
        log_traffic(self.command, host, self.path)
        if not host:
            self.send_error(400, "absolute URL required")
            return
        if not self.server.allow_host(host):
            self.send_error(403, f"destination blocked by policy: {host}")
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        employee = self.headers.get("X-Employee-Id")
        if body and self.server.inspect:
            decision = self.server.inspect(body, self.headers.get("Content-Type", ""), employee, f"{host}{parsed.path or ''}")
            if decision.get("action") == "block":
                payload = json_bytes({"error": "sensitive_data_blocked", "scan": decision.get("scan")})
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if decision.get("action") == "redact" and decision.get("body"):
                body = decision["body"]
        self._forward_http(parsed, body)

    def _forward_http(self, parsed, body: bytes) -> None:
        import urllib.error
        import urllib.request

        url = self.path
        headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "proxy-connection", "content-length"}}
        request = urllib.request.Request(url, data=body or None, method=self.command, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {"transfer-encoding", "content-encoding"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        except urllib.error.HTTPError as error:
            raw = error.read() or b""
            self.send_response(error.code)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)


def log_traffic(method: str, host: str, path: str) -> None:
    try:
        TRAFFIC_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": method,
            "host": host,
            "path": path[:200],
        }
        with TRAFFIC_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        pass


def json_bytes(payload: dict) -> bytes:
    import json

    return json.dumps(payload).encode("utf-8")


def _tunnel(client: socket.socket, upstream: socket.socket) -> None:
    sockets = [client, upstream]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 30)
            if not readable:
                break
            for sock in readable:
                other = upstream if sock is client else client
                try:
                    data = sock.recv(65536)
                except (ConnectionResetError, ConnectionAbortedError, OSError):
                    return
                if not data:
                    return
                try:
                    other.sendall(data)
                except (ConnectionResetError, ConnectionAbortedError, OSError):
                    return
    finally:
        client.close()
        upstream.close()


class GateProxyServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        inspect: Callable | None,
        *,
        allow_all: bool = True,
        extra_hosts: set[str] | None = None,
        mitm: bool = True,
    ) -> None:
        super().__init__(address, ProxyHandler)
        self.inspect = inspect
        self.allow_all = allow_all
        self.allowed = DEFAULT_AI_HOSTS | (extra_hosts or set())
        self.mitm = mitm

    def allow_host(self, host: str) -> bool:
        if self.allow_all:
            return True
        return host in self.allowed or host.endswith(".openai.com")


def start_proxy(
    host: str,
    port: int,
    inspect: Callable | None,
    *,
    allow_all: bool = True,
    mitm: bool = True,
) -> GateProxyServer:
    server = GateProxyServer((host, port), inspect, allow_all=allow_all, mitm=mitm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
