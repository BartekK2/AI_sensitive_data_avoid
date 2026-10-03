"""Company outbound gate for AI SDKs and agents.

Agents do not talk to OpenAI / Anthropic / Gemini directly. They point
OPENAI_BASE_URL (or the sibling vars) at this process. We scan the prompt
with Laya, then forward or reject.

This is not a TLS break of Messenger. It is the path that works for
LangChain, the OpenAI SDK, background agents and internal tools.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from types import SimpleNamespace
from typing import Any, Callable

from .payloads import (
    actor_from_blob,
    extract_texts,
    is_critical_scan,
    national_id_digits,
    join_texts,
    looks_like_vendor_rpc,
    prompt_for_gate,
    rewrite_strings,
    should_scan_destination,
)

try:
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse, Response
except ImportError:  # optional until `net` / `serve` is used
    HTTPException = Request = JSONResponse = Response = None  # type: ignore

UPSTREAM = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "groq": "https://api.groq.com/openai",
    "mistral": "https://api.mistral.ai",
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
    "host",
    "content-length",
}


def map_upstream(path: str) -> tuple[str, str] | None:
    trimmed = path.lstrip("/")
    for name, base in UPSTREAM.items():
        if trimmed == name or trimmed.startswith(name + "/"):
            rest = trimmed[len(name):]
            return name, base.rstrip("/") + rest
    return None


def filter_headers(headers: dict[str, str]) -> dict[str, str]:
    out = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP or lowered.startswith("x-helios-") or lowered == "x-employee-id":
            continue
        out[key] = value
    return out


def default_forward(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()) if error.headers else {}, error.read() or b""


def inspect_and_maybe_redact(
    raw: bytes,
    content_type: str,
    run_scan: Callable,
    employee_id: str | None,
    destination: str,
) -> dict[str, Any]:
    if not should_scan_destination(destination):
        return {"action": "allow", "body": raw, "scan": None, "texts": []}
    payload = parse_payload(raw, content_type)
    text = prompt_for_gate(payload, raw, destination)
    if not text.strip():
        return {"action": "allow", "body": raw, "scan": None, "texts": []}
    actor = actor_from_blob(raw)
    scan = run_scan(
        SimpleNamespace(
            text=text,
            threshold=0.5,
            region="PL",
            locale="pl",
            collapse=False,
            strict=None,
            employee_id=employee_id,
            employee_email=actor.get("email"),
            actor_name=actor.get("name"),
            actor_team=actor.get("team"),
            destination=destination,
            record=True,
        )
    )
    action = scan.get("action") or "allow"
    vendor = looks_like_vendor_rpc(destination)
    identifier = national_id_digits(text)
    if vendor and identifier and not is_critical_scan(scan):
        entities = list(scan.get("entities") or [])
        entities.append(
            {
                "text": identifier,
                "label": "pesel",
                "category": "government_id",
                "risk": "critical",
            }
        )
        scan = {**scan, "action": "block", "risk": "critical", "entities": entities}
        action = "block"
    if action == "block" or (vendor and is_critical_scan(scan)):
        if vendor and not is_critical_scan(scan):
            return {"action": "allow", "body": raw, "scan": scan, "texts": [text]}
        return {"action": "block", "body": raw, "scan": scan, "texts": [text]}
    if vendor:
        return {"action": "allow", "body": raw, "scan": scan, "texts": [text]}
    if action == "redact" and payload is not None:
        mapping = {
            entity.get("text"): f"[{(entity.get('label') or 'redacted').upper()}]"
            for entity in scan.get("entities") or []
            if entity.get("text")
        }
        rewritten = rewrite_strings(payload, lambda value: replace_all(value, mapping))
        return {
            "action": "redact",
            "body": json.dumps(rewritten, ensure_ascii=False).encode("utf-8"),
            "scan": scan,
            "texts": [text],
        }
    return {"action": action, "body": raw, "scan": scan, "texts": [text]}


def parse_payload(raw: bytes, content_type: str) -> Any:
    if not raw:
        return None
    if "json" in (content_type or "") or raw[:1] in {b"{", b"["}:
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def decode_payload(raw: bytes, content_type: str) -> tuple[str, Any]:
    payload = parse_payload(raw, content_type)
    if payload is not None:
        extracted = join_texts(extract_texts(payload))
        return extracted or raw.decode("utf-8", errors="replace"), payload
    return raw.decode("utf-8", errors="replace") if raw else "", None


def replace_all(value: str, mapping: dict[str, str]) -> str:
    out = value
    for needle, token in sorted(mapping.items(), key=lambda item: len(item[0] or ""), reverse=True):
        if needle:
            out = out.replace(needle, token)
    return out


def register_net_routes(app, *, run_scan: Callable, forward: Callable = default_forward) -> None:
    if Request is None:
        raise RuntimeError("pip install fastapi")

    @app.get("/net/health")
    def net_health() -> dict[str, Any]:
        return {
            "ok": True,
            "mode": "api-gateway + http-proxy",
            "upstreams": list(UPSTREAM),
            "env": {
                "OPENAI_BASE_URL": "http://127.0.0.1:8080/net/openai/v1",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080/net/anthropic",
                "HTTP_PROXY": "http://127.0.0.1:8888",
                "HTTPS_PROXY": "http://127.0.0.1:8888",
            },
        }

    @app.api_route("/net/{vendor}/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def vendor_proxy(vendor: str, full_path: str, request: Request):
        mapped = map_upstream(f"{vendor}/{full_path}")
        if mapped is None:
            raise HTTPException(status_code=404, detail=f"unknown vendor '{vendor}'")
        name, url = mapped
        raw = await request.body()
        employee = request.headers.get("x-employee-id") or request.headers.get("x-helios-employee")
        gated = inspect_and_maybe_redact(raw, request.headers.get("content-type", ""), run_scan, employee, name)
        if gated["action"] == "block":
            return JSONResponse(
                status_code=403,
                content={"error": "sensitive_data_blocked", "scan": gated["scan"]},
            )
        status, headers, upstream = forward(
            request.method,
            url,
            filter_headers({key: value for key, value in request.headers.items()}),
            gated["body"],
        )
        skip = {"content-encoding", "transfer-encoding", "content-length"}
        safe = {key: value for key, value in headers.items() if key.lower() not in skip}
        return Response(content=upstream, status_code=status, headers=safe)
