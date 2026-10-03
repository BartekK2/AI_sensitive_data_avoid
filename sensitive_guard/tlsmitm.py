"""Decrypt HTTPS to a short allow-list of AI hosts and scan the request body."""

from __future__ import annotations

import json
import socket
import ssl
from typing import Callable

INTERCEPT_MARKERS = (
    "cloudcode-pa",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "api.openai.com",
    "api.anthropic.com",
    "api.groq.com",
    "api.mistral.ai",
    "openrouter.ai",
    "api.deepseek.com",
    "api.x.ai",
)


def should_intercept(host: str) -> bool:
    lowered = (host or "").lower().rstrip(".")
    if not lowered:
        return False
    return any(marker in lowered for marker in INTERCEPT_MARKERS)


def is_prompt_rpc(path: str) -> bool:
    lowered = (path or "").lower()
    return any(
        marker in lowered
        for marker in (
            "streamgeneratecontent",
            "generatecontent",
            "chat/completions",
            "/v1/messages",
        )
    )


def recv_until(sock, separator: bytes, limit: int = 1_048_576) -> bytes:
    buf = b""
    while separator not in buf:
        chunk = sock.recv(8192)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            break
    return buf


def read_request(sock) -> tuple[bytes, bytes, bytes] | None:
    raw = recv_until(sock, b"\r\n\r\n")
    if b"\r\n\r\n" not in raw:
        return None
    head, rest = raw.split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    if not lines:
        return None
    headers = {}
    for line in lines[1:]:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        headers[key.decode("latin-1").lower()] = value.strip()
    body = rest
    if headers.get("transfer-encoding", b"").lower() == b"chunked":
        body = read_chunked(sock, rest)
    else:
        length = int(headers.get("content-length", b"0") or b"0")
        while len(body) < length:
            chunk = sock.recv(length - len(body))
            if not chunk:
                break
            body += chunk
    return lines[0], head, body


def read_chunked(sock, extra: bytes) -> bytes:
    buf = extra
    out = b""
    while True:
        if b"\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            continue
        line, buf = buf.split(b"\r\n", 1)
        size = int(line.split(b";", 1)[0] or b"0", 16)
        if size == 0:
            return out
        while len(buf) < size + 2:
            chunk = sock.recv(size + 2 - len(buf))
            if not chunk:
                break
            buf += chunk
        out += buf[:size]
        buf = buf[size + 2 :]


def pump(src, dst, nbytes: int | None = None) -> None:
    remaining = nbytes
    while remaining is None or remaining > 0:
        want = 65536 if remaining is None else min(65536, remaining)
        data = src.recv(want)
        if not data:
            return
        dst.sendall(data)
        if remaining is not None:
            remaining -= len(data)


def header_map(header_block: bytes) -> dict[str, bytes]:
    out = {}
    for line in header_block.split(b"\r\n")[1:]:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        out[key.decode("latin-1").lower()] = value.strip()
    return out


def replace_content_length(header_block: bytes, length: int) -> bytes:
    lines = header_block.split(b"\r\n")
    out = [lines[0]]
    found = False
    for line in lines[1:]:
        if line.lower().startswith(b"content-length:"):
            out.append(f"Content-Length: {length}".encode("ascii"))
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"Content-Length: {length}".encode("ascii"))
    return b"\r\n".join(out)


def last_chunk_seen(data: bytes) -> bool:
    return b"\r\n0\r\n\r\n" in data or data == b"0\r\n\r\n" or data.endswith(b"0\r\n\r\n")


def drain_chunked(src, dst, already: bytes) -> None:
    buf = already
    while not last_chunk_seen(buf):
        chunk = src.recv(65536)
        if not chunk:
            return
        dst.sendall(chunk)
        buf += chunk


HOP_HEADERS = {
    "connection",
    "proxy-connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailers",
    "upgrade",
    "expect",
    "host",
    "content-length",
}


def relay_http11(
    client,
    host: str,
    inspect: Callable | None,
    log: Callable | None = None,
    upstream=None,
) -> None:
    client.settimeout(180)
    while True:
        parsed = read_request(client)
        if parsed is None:
            return
        request_line, header_block, body = parsed
        if request_line.startswith(b"PRI *"):
            # Client ignored ALPN http/1.1 and sent an HTTP/2 preface.
            # A fake HTTP/1.1 403 on that socket kills the whole agent.
            # Drop the connection; the client retries and the next one is HTTP/1.1, which we scan.
            print("[proxy] HTTP/2 preface on", host, "— zamykam, klient ma zejść na HTTP/1.1")
            return
        parts = request_line.split(b" ")
        method = parts[0].decode("latin-1") if parts else "?"
        path = parts[1].decode("latin-1") if len(parts) > 1 else "/"
        if log:
            log(f"MITM {method}", host, path[:200])
        print("[proxy] MITM", method, host, path[:80], "body", len(body))
        prompt = is_prompt_rpc(path) or (body and b"USER_REQUEST" in body)
        if body and inspect and (prompt or len(body) > 50):
            headers = header_map(header_block)
            content_type = headers.get("content-type", b"").decode("latin-1")
            try:
                decision = inspect(body, content_type, None, f"{host}{path}")
            except Exception as error:
                print("[proxy] MITM inspect failed, passing through", host, error)
                decision = {"action": "allow"}
            action = decision.get("action")
            print("[proxy] MITM decision", action, "scan", (decision.get("scan") or {}).get("action"), path[:60])
            if action == "block":
                payload = json.dumps(
                    {"error": "sensitive_data_blocked", "scan": decision.get("scan")},
                    ensure_ascii=False,
                ).encode("utf-8")
                client.sendall(
                    b"HTTP/1.1 403 Forbidden\r\n"
                    b"Content-Type: application/json; charset=utf-8\r\n"
                    b"Connection: close\r\n"
                    + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                    + payload
                )
                print("[proxy] MITM block", host, path[:80])
                return
        if prompt:
            forward_to_origin(client, host, method, path, header_block, body)
            return
        if upstream is None:
            exchange_http11(client, host, header_block, body)
            continue
        upstream.sendall(header_block + b"\r\n\r\n" + body)
        raw = recv_until(upstream, b"\r\n\r\n")
        if b"\r\n\r\n" not in raw:
            return
        resp_head, rest = raw.split(b"\r\n\r\n", 1)
        client.sendall(resp_head + b"\r\n\r\n" + rest)
        resp_headers = header_map(resp_head)
        encoding = resp_headers.get("transfer-encoding", b"").lower()
        if encoding == b"chunked":
            drain_chunked(upstream, client, rest)
        elif resp_headers.get("content-length"):
            left = int(resp_headers["content-length"]) - len(rest)
            if left > 0:
                pump(upstream, client, left)
        else:
            pump(upstream, client)
        if resp_headers.get("connection", b"").lower() == b"close":
            return


def exchange_http11(client, host: str, header_block: bytes, body: bytes) -> None:
    ctx = ssl.create_default_context()
    try:
        ctx.set_alpn_protocols(["http/1.1"])
    except ssl.SSLError:
        pass
    raw = socket.create_connection((host, 443), timeout=20)
    upstream = ctx.wrap_socket(raw, server_hostname=host)
    try:
        upstream.sendall(header_block + b"\r\n\r\n" + body)
        first = recv_until(upstream, b"\r\n\r\n")
        if b"\r\n\r\n" not in first:
            return
        resp_head, rest = first.split(b"\r\n\r\n", 1)
        client.sendall(resp_head + b"\r\n\r\n" + rest)
        resp_headers = header_map(resp_head)
        encoding = resp_headers.get("transfer-encoding", b"").lower()
        if encoding == b"chunked":
            drain_chunked(upstream, client, rest)
        elif resp_headers.get("content-length"):
            left = int(resp_headers["content-length"]) - len(rest)
            if left > 0:
                pump(upstream, client, left)
        else:
            pump(upstream, client)
    finally:
        try:
            upstream.close()
        except OSError:
            pass


def origin_headers(header_block: bytes, body: bytes) -> dict[str, str]:
    headers = {}
    for key, value in header_map(header_block).items():
        if key in HOP_HEADERS:
            continue
        headers[key] = value.decode("latin-1")
    headers["content-length"] = str(len(body))
    headers.pop("accept-encoding", None)
    return headers


def forward_to_origin(client, host: str, method: str, path: str, header_block: bytes, body: bytes) -> None:
    headers = origin_headers(header_block, body)
    url = f"https://{host}{path}"
    try:
        import httpx
    except ImportError:
        print("[proxy] httpx missing, cannot stream", host, path[:60])
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        return
    print("[proxy] MITM origin", method, url[:120])
    try:
        with httpx.Client(http2=True, timeout=httpx.Timeout(180.0, connect=20.0)) as session:
            with session.stream(method, url, headers=headers, content=body) as resp:
                reason = resp.reason_phrase or "OK"
                client.sendall(f"HTTP/1.1 {resp.status_code} {reason}\r\n".encode("ascii", "replace"))
                for key, value in resp.headers.items():
                    if key.lower() in {"transfer-encoding", "content-length", "connection"}:
                        continue
                    client.sendall(f"{key}: {value}\r\n".encode("latin-1", "replace"))
                client.sendall(b"Connection: close\r\n\r\n")
                for chunk in resp.iter_raw():
                    if chunk:
                        client.sendall(chunk)
                print("[proxy] MITM origin done", resp.status_code, host, path[:60])
    except Exception as error:
        print("[proxy] MITM origin failed", host, path[:60], error)
        try:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except OSError:
            pass


def client_ssl_context(cert_path, key_path) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert_path), str(key_path))
    # Force HTTP/1.1 — if h2 is negotiated we cannot inspect frames.
    # This must not be silenced; if set_alpn_protocols fails the server
    # would silently accept h2 and all traffic would bypass scanning.
    ctx.set_alpn_protocols(["http/1.1"])
    return ctx


def upstream_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # Also restrict upstream to h1.1 so responses are parseable.
    try:
        ctx.set_alpn_protocols(["http/1.1"])
    except ssl.SSLError:
        pass
    return ctx
