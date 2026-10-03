"""Company outbound gate for AI SDKs and agents.

Agents do not talk to OpenAI / Anthropic / Gemini directly. They point
OPENAI_BASE_URL (or the sibling vars) at this process. We scan the prompt
with the policy stack, then forward or reject. Responses can be scanned too.
"""

from __future__ import annotations

import json
import socket
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
    "ollama": "http://127.0.0.1:11434",
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

STATUS_FOR_KIND = {
    "budget": 429,
    "rate_limit": 429,
    "loop": 429,
    "model": 403,
    "memory": 403,
    "tool": 403,
    "attack": 403,
    "pii": 403,
}

ERROR_FOR_KIND = {
    "budget": "budget_exceeded",
    "rate_limit": "rate_limited",
    "loop": "agent_loop_detected",
    "model": "model_not_allowed",
    "memory": "memory_isolation",
    "tool": "tool_not_allowed",
    "attack": "attack_signature_blocked",
    "pii": "sensitive_data_blocked",
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


def model_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        model = payload.get("model")
        if isinstance(model, str) and model:
            return model
    return None


def tool_names_from_payload(payload: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(payload, dict):
        return names
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else None
        name = (function or {}).get("name") or tool.get("name")
        if isinstance(name, str):
            names.append(name)
    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                name = function.get("name") or call.get("name")
                if isinstance(name, str):
                    names.append(name)
    return names


def foreign_identity(raw: bytes, employee_id: str | None, store) -> str | None:
    """Prompt context that names a different employee than the request header."""
    if not employee_id or store is None:
        return None
    try:
        blob = raw.decode("utf-8", errors="replace")
    except Exception:
        return None
    lowered = blob.lower()
    for employee in store.list_collection("employees"):
        other = employee.get("id")
        if not other or other == employee_id:
            continue
        marker = f"employee_id={other}".lower()
        marker_json = f'"employee_id": "{other}"'.lower()
        marker_json2 = f'"employee_id":"{other}"'.lower()
        if marker in lowered or marker_json in lowered or marker_json2 in lowered:
            return other
    return None


def kind_of(scan: dict[str, Any] | None) -> str:
    return (scan or {}).get("kind") or "pii"


def custom_topic_hit(scan: dict[str, Any] | None) -> bool:
    """A category the admin added by name. Vendor traffic must not quietly let it through."""
    for entity in (scan or {}).get("entities") or []:
        if entity.get("source") == "custom" and entity.get("action") == "block":
            return True
    return False


def inspect_and_maybe_redact(
    raw: bytes,
    content_type: str,
    run_scan: Callable,
    employee_id: str | None,
    destination: str,
    *,
    policy=None,
    store=None,
) -> dict[str, Any]:
    if not should_scan_destination(destination):
        return {"action": "allow", "body": raw, "scan": None, "texts": []}
    payload = parse_payload(raw, content_type)
    model = model_from_payload(payload)

    if policy is not None and store is not None and policy.control_enabled("tool_allowlist") and policy.agent.allowed_tools is not None:
        tools = tool_names_from_payload(payload)
        rejected = [name for name in tools if name not in policy.agent.allowed_tools]
        if rejected:
            scan = run_scan(SimpleNamespace(
                text=f"tool call(s) not allowed: {', '.join(rejected)}", threshold=None, region="PL", locale="pl",
                collapse=False, strict=None, employee_id=employee_id, employee_email=None, actor_name=None,
                actor_team=None, destination=destination, model=model, record=True, direction="input",
            ))
            scan = {**scan, "action": "block", "kind": "tool", "risk": "high",
                    "blocked_reason": f"tool call(s) not allowed: {', '.join(rejected)}",
                    "controls_fired": sorted(set((scan.get("controls_fired") or []) + ["tool_allowlist"]))}
            return {"action": "block", "body": raw, "scan": scan, "texts": [], "kind": "tool"}

    if policy is not None and store is not None and policy.control_enabled("memory_isolation") and policy.agent.memory_isolation:
        foreign = foreign_identity(raw, employee_id, store)
        if foreign:
            scan = run_scan(SimpleNamespace(
                text=f"prompt carries context of another employee ({foreign})", threshold=None, region="PL", locale="pl",
                collapse=False, strict=None, employee_id=employee_id, employee_email=None, actor_name=None,
                actor_team=None, destination=destination, model=model, record=True, direction="input",
            ))
            scan = {**scan, "action": "block", "kind": "memory", "risk": "critical",
                    "blocked_reason": f"memory isolation: prompt references employee {foreign}",
                    "controls_fired": sorted(set((scan.get("controls_fired") or []) + ["memory_isolation"]))}
            return {"action": "block", "body": raw, "scan": scan, "texts": [], "kind": "memory"}

    text = prompt_for_gate(payload, raw, destination)
    if not text.strip():
        return {"action": "allow", "body": raw, "scan": None, "texts": []}
    actor = actor_from_blob(raw)
    scan = run_scan(
        SimpleNamespace(
            text=text,
            threshold=None,
            region="PL",
            locale="pl",
            collapse=False,
            strict=None,
            employee_id=employee_id,
            employee_email=actor.get("email"),
            actor_name=actor.get("name"),
            actor_team=actor.get("team"),
            destination=destination,
            model=model,
            record=True,
            direction="input",
        )
    )
    action = scan.get("action") or "allow"
    kind = kind_of(scan)
    if kind not in {"pii", "attack"} and action == "block":
        return {"action": "block", "body": raw, "scan": scan, "texts": [text], "kind": kind}
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
        if vendor and not is_critical_scan(scan) and not custom_topic_hit(scan):
            return {"action": "allow", "body": raw, "scan": scan, "texts": [text], "kind": kind}
        return {"action": "block", "body": raw, "scan": scan, "texts": [text], "kind": kind}
    if vendor:
        return {"action": "allow", "body": raw, "scan": scan, "texts": [text], "kind": kind}
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
            "kind": kind,
        }
    return {"action": action, "body": raw, "scan": scan, "texts": [text], "kind": kind}


def response_text(payload: Any) -> str:
    """Assistant text from an OpenAI / Anthropic / Gemini style response."""
    chunks: list[str] = []
    if isinstance(payload, dict):
        for choice in payload.get("choices") or []:
            if isinstance(choice, dict):
                message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                if isinstance(message.get("content"), str):
                    chunks.append(message["content"])
                if isinstance(choice.get("text"), str):
                    chunks.append(choice["text"])
        for block in payload.get("content") or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                chunks.append(block["text"])
        for candidate in payload.get("candidates") or []:
            if isinstance(candidate, dict):
                content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
                for part in content.get("parts") or []:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
        if isinstance(payload.get("response"), str):
            chunks.append(payload["response"])
    if not chunks:
        chunks = extract_texts(payload)
    return join_texts([chunk for chunk in chunks if chunk and chunk.strip()])


def scan_response(
    raw: bytes,
    content_type: str,
    run_scan: Callable,
    employee_id: str | None,
    destination: str,
    model: str | None,
) -> tuple[bytes, dict[str, Any] | None]:
    payload = parse_payload(raw, content_type)
    if payload is None:
        return raw, None
    text = response_text(payload)
    if not text.strip():
        return raw, None
    scan = run_scan(
        SimpleNamespace(
            text=text, threshold=None, region="PL", locale="pl", collapse=False, strict=None,
            employee_id=employee_id, employee_email=None, actor_name=None, actor_team=None,
            destination=destination, model=model, record=True, direction="output",
        )
    )
    action = scan.get("action") or "allow"
    if action == "allow":
        return raw, scan
    mapping = {
        entity.get("text"): f"[{(entity.get('label') or 'redacted').upper()}]"
        for entity in scan.get("entities") or []
        if entity.get("text")
    }
    if not mapping:
        return raw, scan
    rewritten = rewrite_strings(payload, lambda value: replace_all(value, mapping))
    return json.dumps(rewritten, ensure_ascii=False).encode("utf-8"), scan


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


def blocked_response(gated: dict[str, Any]):
    scan = gated.get("scan") or {}
    kind = gated.get("kind") or kind_of(scan)
    status = STATUS_FOR_KIND.get(kind, 403)
    return JSONResponse(
        status_code=status,
        content={
            "error": ERROR_FOR_KIND.get(kind, "sensitive_data_blocked"),
            "kind": kind,
            "reason": scan.get("blocked_reason"),
            "request_id": scan.get("request_id"),
            "incident_id": (scan.get("incident") or {}).get("id"),
            "scan": scan,
        },
        headers={"X-Helios-Policy-Version": str(scan.get("policy_version") or "")},
    )


def register_net_routes(app, *, run_scan: Callable, forward: Callable = default_forward, ctx=None) -> None:
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
                "OLLAMA_HOST": "http://127.0.0.1:8080/net/ollama",
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
        policy = ctx.policy.load() if ctx is not None else None
        store = ctx.store if ctx is not None else None
        gated = inspect_and_maybe_redact(
            raw, request.headers.get("content-type", ""), run_scan, employee, name, policy=policy, store=store,
        )
        if gated["action"] == "block":
            return blocked_response(gated)
        model = model_from_payload(parse_payload(raw, request.headers.get("content-type", "")))
        try:
            status, headers, upstream = forward(
                request.method,
                url,
                filter_headers({key: value for key, value in request.headers.items()}),
                gated["body"],
            )
        except (urllib.error.URLError, socket.timeout, OSError) as error:
            if ctx is not None:
                ctx.telemetry.bump("upstream_timeouts" if isinstance(error, socket.timeout) else "upstream_errors")
            return JSONResponse(status_code=502, content={"error": "upstream_unavailable", "detail": str(error)})
        if ctx is not None and status >= 500:
            ctx.telemetry.bump("upstream_errors")
        skip = {"content-encoding", "transfer-encoding", "content-length"}
        safe = {key: value for key, value in headers.items() if key.lower() not in skip}
        scan = gated.get("scan") or {}
        if scan.get("policy_version") is not None:
            safe["X-Helios-Policy-Version"] = str(scan["policy_version"])
        if scan.get("request_id"):
            safe["X-Helios-Request-Id"] = str(scan["request_id"])
        if gated["action"] == "redact":
            safe["X-Helios-Action"] = "redact"
        if (
            policy is not None
            and policy.scan_output
            and policy.control_enabled("output_scan")
            and status < 400
            and "json" in (headers.get("Content-Type") or headers.get("content-type") or "")
        ):
            upstream, out_scan = scan_response(upstream, "application/json", run_scan, employee, name, model)
            if out_scan and out_scan.get("action") != "allow":
                safe["X-Helios-Output-Action"] = out_scan["action"]
        return Response(content=upstream, status_code=status, headers=safe)
