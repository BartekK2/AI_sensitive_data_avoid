"""The gated scan: policy + workspace + signatures + budget + audit + telemetry.

Every entry point (REST /v1/scan, /net gateway, HTTP proxy, TLS MITM) ends up
in `execute_gated_scan`, so this is where decisions, incidents and the audit
trail are produced.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from pathlib import Path
from typing import Any

from .audit import AuditLog, mask_value
from .budget import BudgetTracker, estimate_tokens
from .policy import CONTROL_BY_ID, LABEL_CONTROL, Policy, PolicyStore, strongest
from .signatures import SignatureStore
from .taxonomy import GateAction, RiskLevel
from .telemetry import Stopwatch, Telemetry

CHECKSUM_LABELS = {"pesel", "nip", "regon", "iban", "credit card number", "social security number", "tax number"}
SECRET_LABELS = {"api key", "access token", "private key", "password"}


class GateContext:
    """All per-deployment services, derived from the workspace file location."""

    _registry: dict[str, "GateContext"] = {}
    _registry_lock = threading.Lock()

    def __init__(self, store, *, root: Path | None = None) -> None:
        self.store = store
        base = Path(root) if root else Path(store.path).parent
        self.policy = PolicyStore(base / "policy.json")
        self.signatures = SignatureStore(base / "signatures.json")
        self.audit = AuditLog(base / "audit.jsonl")
        self.telemetry = Telemetry()
        self.budget = BudgetTracker(store)
        self._recent: dict[str, list[float]] = {}
        self._recent_lock = threading.Lock()
        self.telemetry.hydrate(self.audit.tail(2000))

    @classmethod
    def for_store(cls, store) -> "GateContext":
        key = str(Path(store.path).resolve())
        with cls._registry_lock:
            ctx = cls._registry.get(key)
            if ctx is None:
                ctx = cls(store)
                cls._registry[key] = ctx
            return ctx

    def loop_hit(self, key: str, *, window_s: int, max_repeats: int) -> tuple[bool, int]:
        import time

        now = time.monotonic()
        with self._recent_lock:
            bucket = self._recent.setdefault(key, [])
            bucket[:] = [ts for ts in bucket if now - ts <= window_s]
            bucket.append(now)
            return len(bucket) > max_repeats, len(bucket)


def detected_by_for(entity: dict[str, Any]) -> str:
    if entity.get("detected_by"):
        return entity["detected_by"]
    label = (entity.get("label") or "").lower()
    source = (entity.get("source") or "").lower()
    if source == "signature":
        return "signature"
    if label in CHECKSUM_LABELS:
        return "checksum"
    if label in SECRET_LABELS:
        return "regex"
    if source.endswith("+rule"):
        return "rule"
    if source.startswith("laya"):
        return "laya"
    return "heuristic"


def control_for(entity: dict[str, Any]) -> str:
    if entity.get("control"):
        return entity["control"]
    if entity.get("source") == "signature":
        return "signatures"
    return LABEL_CONTROL.get((entity.get("label") or "").lower(), "pii_classifier")


def dedupe_key(employee_id: str | None, destination: str, labels: list[str], text: str) -> str:
    import re

    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())[:200]
    blob = "|".join([employee_id or "-", (destination or "").lower(), ",".join(sorted(labels)), normalized])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def excerpt_of(text: str, limit: int = 280) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _blocked_payload(
    *,
    text: str,
    kind: str,
    reason: str,
    control: str,
    backend: str,
    employee: dict[str, Any] | None,
    role: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "text": text,
        "entities": [],
        "categories": [],
        "risk": "critical" if kind in {"attack", "memory"} else "high",
        "action": "block",
        "document_type": "unknown",
        "backend": backend,
        "candidates": 0,
        "redacted": excerpt_of(text),
        "policy": {},
        "skipped": [],
        "policy_applied": True,
        "employee": employee,
        "role": role,
        "incident": None,
        "kind": kind,
        "blocked_reason": reason,
        "controls_fired": [control],
    }


def execute_gated_scan(layer, store, body, ctx: GateContext | None = None) -> dict[str, Any]:
    from .models import Entity, summarize_categories
    from .workspace import apply_workspace_policy, record_incident, risk_from_entities

    ctx = ctx or GateContext.for_store(store)
    policy: Policy = ctx.policy.load()
    watch = Stopwatch()
    request_id = getattr(body, "request_id", None) or f"req_{uuid.uuid4().hex[:10]}"
    text = getattr(body, "text", "") or ""
    destination = getattr(body, "destination", "ai_chat") or "ai_chat"
    direction = getattr(body, "direction", None) or "input"
    model = getattr(body, "model", None)
    record = bool(getattr(body, "record", False))

    employee = store.employee_by_id_or_email(getattr(body, "employee_id", None), getattr(body, "employee_email", None))
    actor_name = getattr(body, "actor_name", None)
    actor_team = getattr(body, "actor_team", None)
    if employee is None and actor_name:
        employee = {"id": None, "name": actor_name, "team": actor_team or "—", "role_id": None}
    role = store.role_for(employee)
    if role is None and actor_name and employee and not employee.get("role_id"):
        role = {"name": "Antigravity"}

    tokens = estimate_tokens(text)
    budget_cfg = policy.budgets
    budget_note: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None

    # 1. Model allow-list (deterministic).
    if model and not policy.model_allowed(model) and direction == "input":
        payload = _blocked_payload(
            text=text, kind="model", reason=f"model '{model}' is not on the allow-list", control="model_allowlist",
            backend=layer.backend, employee=employee, role=role,
        )

    # 2. Rate limit and token budget (deterministic).
    if payload is None and direction == "input" and policy.control_enabled("rate_limit") and record:
        rate_key = (employee or {}).get("id") or (employee or {}).get("name") or "unknown"
        allowed, count = ctx.budget.check_rate(budget_cfg, rate_key)
        if not allowed:
            payload = _blocked_payload(
                text=text, kind="rate_limit", reason=f"rate limit: {count} requests in the last minute", control="rate_limit",
                backend=layer.backend, employee=employee, role=role,
            )
    if payload is None and direction == "input" and policy.control_enabled("budget") and record:
        verdict = ctx.budget.check(budget_cfg, employee=employee, model=model, tokens=tokens)
        budget_note = verdict
        if not verdict.get("allowed"):
            payload = _blocked_payload(
                text=text, kind="budget", reason=verdict.get("reason") or "budget exceeded", control="budget",
                backend=layer.backend, employee=employee, role=role,
            )

    # 3. Loop guard (same prompt hammering the gate).
    if payload is None and direction == "input" and policy.control_enabled("loop_guard") and record and text.strip():
        loop_key = dedupe_key((employee or {}).get("id"), destination, [], text)
        hit, repeats = ctx.loop_hit(loop_key, window_s=policy.agent.loop_window_s, max_repeats=policy.agent.loop_max_repeats)
        if hit:
            payload = _blocked_payload(
                text=text, kind="loop", reason=f"same prompt repeated {repeats}x within {policy.agent.loop_window_s}s", control="loop_guard",
                backend=layer.backend, employee=employee, role=role,
            )

    controls_fired: list[str] = []
    if payload is None:
        requested = getattr(body, "threshold", None)
        threshold = policy.threshold if requested is None else requested
        strict_flag = getattr(body, "strict", None)
        result = layer.scan(
            text,
            threshold=threshold,
            region=getattr(body, "region", "PL") or "PL",
            locale=getattr(body, "locale", "pl") or "pl",
            collapse=bool(getattr(body, "collapse", False)),
        )
        payload = result.model_dump()
        entities = payload.get("entities") or []

        # 4. Attack signatures (deterministic feed).
        if policy.control_enabled("signatures"):
            for hit in ctx.signatures.match(text):
                entities.append(
                    {
                        "start": hit["start"],
                        "end": hit["end"],
                        "text": hit["text"],
                        "label": hit["label"],
                        "score": 1.0,
                        "category": "attack",
                        "risk": hit["severity"] if hit["severity"] in {"low", "medium", "high", "critical"} else "critical",
                        "legal": "OWASP LLM Top 10",
                        "families": [hit["type"]],
                        "source": "signature",
                        "signature_id": hit["signature_id"],
                        "signature_name": hit["name"],
                    }
                )

        # 4b. Custom category patterns from the workspace (judges can add "health" with a regex).
        if policy.control_enabled("custom_patterns"):
            import re as _re

            from .taxonomy import SensitivityCategory

            known = {item.value for item in SensitivityCategory}
            for category in store.list_collection("categories"):
                if not category.get("enabled", True) or not category.get("patterns"):
                    continue
                key = category.get("key") or "other"
                for pattern in category["patterns"]:
                    try:
                        compiled = _re.compile(pattern, _re.I)
                    except _re.error:
                        continue
                    for found in compiled.finditer(text):
                        if not found.group(0).strip():
                            continue
                        entities.append(
                            {
                                "start": found.start(),
                                "end": found.end(),
                                "text": found.group(0),
                                "label": category.get("label") or key,
                                "score": 0.9,
                                "category": key if key in known else "other",
                                "risk": category.get("risk") or "medium",
                                "legal": None,
                                "families": ["CUSTOM"],
                                "source": "custom",
                                "detected_by": "regex",
                                "control": "custom_patterns",
                            }
                        )

        # 5. Disabled deterministic / semantic controls drop their entities.
        disabled = set(policy.disabled_controls())
        remaining: list[dict[str, Any]] = []
        skipped_controls: list[dict[str, Any]] = []
        for entity in entities:
            control = control_for(entity)
            if control in disabled:
                skipped_controls.append({**entity, "skipped_by": "control_disabled", "control": control})
                continue
            entity["detected_by"] = detected_by_for(entity)
            entity["control"] = control
            remaining.append(entity)

        # 6. Workspace policy: disabled categories, role exceptions, whitelist.
        kept, skipped = apply_workspace_policy(remaining, store=store, employee=employee)
        if not policy.control_enabled("whitelist"):
            back = [item for item in skipped if item.get("skipped_by") == "whitelist"]
            skipped = [item for item in skipped if item.get("skipped_by") != "whitelist"]
            kept.extend({k: v for k, v in item.items() if k not in {"skipped_by", "rule_id"}} for item in back)
        if not policy.control_enabled("roles"):
            back = [item for item in skipped if item.get("skipped_by") == "role"]
            skipped = [item for item in skipped if item.get("skipped_by") != "role"]
            kept.extend({k: v for k, v in item.items() if k != "skipped_by"} for item in back)
        kept.sort(key=lambda item: item.get("start", 0))
        payload["entities"] = kept
        payload["skipped"] = skipped + skipped_controls
        payload["policy_applied"] = True
        for item in skipped:
            if item.get("skipped_by") == "whitelist":
                controls_fired.append("whitelist")
            elif item.get("skipped_by") == "role":
                controls_fired.append("roles")

        # 7. Per-entity action from the central policy (category overrides, destination overrides, preset).
        if kept:
            rebuilt = [Entity.model_validate({k: v for k, v in item.items() if k in Entity.model_fields}) for item in kept]
            payload["categories"] = [item.model_dump() for item in summarize_categories(rebuilt)]
            risk = risk_from_entities(kept)
            actions = []
            for item in kept:
                entity_action = policy.action_for(item.get("category") or "", item.get("risk") or "medium", destination)
                if strict_flag and entity_action is GateAction.ALLOW:
                    entity_action = GateAction.REDACT
                item["action"] = entity_action.value
                actions.append(entity_action)
                controls_fired.append(item.get("control") or "pii_classifier")
            payload["risk"] = risk.value
            payload["action"] = strongest(actions).value
            if policy.control_enabled("laya_policy") and (payload.get("policy") or {}).get("action") == "block":
                payload["action"] = GateAction.BLOCK.value
                controls_fired.append("laya_policy")
        else:
            payload["categories"] = []
            payload["risk"] = RiskLevel.NONE.value
            payload["action"] = GateAction.ALLOW.value

        from .models import redact_text

        redact_entities = [Entity.model_validate({k: v for k, v in item.items() if k in Entity.model_fields}) for item in kept]
        payload["redacted"] = redact_text(text, redact_entities, locale=getattr(body, "locale", "pl") or "pl", collapse=bool(getattr(body, "collapse", False)))
        payload["kind"] = "attack" if any(item.get("category") == "attack" for item in kept) else "pii"
        payload["blocked_reason"] = None
        if payload["action"] == GateAction.BLOCK.value:
            critical = sorted({item.get("label") for item in kept if item.get("risk") == "critical"})
            payload["blocked_reason"] = (
                f"Blocked: {', '.join(critical)}" if critical else "Blocked by policy"
            )

    payload["employee"] = employee
    payload["role"] = role
    payload["request_id"] = request_id
    payload["direction"] = direction
    payload["destination"] = destination
    payload["model"] = model
    payload["tokens_est"] = tokens
    payload["policy_version"] = policy.version
    payload["preset"] = policy.preset
    payload["threshold_used"] = getattr(body, "threshold", None) if getattr(body, "threshold", None) is not None else policy.threshold
    payload["controls_fired"] = sorted(set(controls_fired or payload.get("controls_fired") or []))
    payload["prompt_excerpt"] = excerpt_of(payload.get("redacted") or text)
    payload["budget"] = {
        "pct": (budget_note or {}).get("pct", 0),
        "warnings": (budget_note or {}).get("warnings", []),
    }
    payload["latency_ms"] = watch.ms()
    payload.setdefault("incident", None)

    blocked = payload["action"] == GateAction.BLOCK.value
    if record:
        if payload["action"] in {GateAction.BLOCK.value, GateAction.REDACT.value}:
            payload["incident"] = record_incident(
                store,
                employee=employee,
                role=role,
                scan=payload,
                destination=destination,
            )
        if direction == "input" and policy.control_enabled("budget"):
            hit = None
            if payload.get("kind") == "budget" and budget_note and budget_note.get("scope"):
                hit = (budget_note["scope"], budget_note["key"])
            ctx.budget.consume(budget_cfg, employee=employee, model=model, tokens=tokens, blocked=blocked, budget_hit=hit)
        event = {
            "request_id": request_id,
            "direction": direction,
            "action": payload["action"],
            "risk": payload["risk"],
            "kind": payload.get("kind") or "pii",
            "employee_id": (employee or {}).get("id"),
            "employee_name": (employee or {}).get("name") or "unknown",
            "team": (employee or {}).get("team") or "—",
            "role_name": (role or {}).get("name") or "—",
            "destination": destination,
            "model": model,
            "categories": [item.get("category") for item in payload.get("categories") or []],
            "labels": sorted({item.get("label") for item in payload.get("entities") or [] if item.get("label")}),
            "controls_fired": payload["controls_fired"],
            "backend": payload.get("backend"),
            "latency_ms": payload["latency_ms"],
            "tokens_est": tokens,
            "policy_version": policy.version,
            "incident_id": (payload.get("incident") or {}).get("id"),
            "excerpt": payload["prompt_excerpt"],
            "masked_values": [mask_value(item.get("text") or "") for item in payload.get("entities") or []],
            "raw_values": [item.get("text") for item in payload.get("entities") or [] if item.get("text")],
            "budget_warnings": payload["budget"]["warnings"],
        }
        ctx.audit.append(event)
        ctx.telemetry.record({**event, "ts": _ts_now()})
        for warning in payload["budget"]["warnings"]:
            ctx.audit.append({"request_id": request_id, "kind": "budget_warning", "action": "warn", **warning,
                              "employee_id": (employee or {}).get("id"), "employee_name": (employee or {}).get("name")})
    return payload


def _ts_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def control_catalog_with_hits(ctx: GateContext) -> list[dict[str, Any]]:
    described = ctx.policy.describe()
    hits: dict[str, int] = {}
    last: dict[str, str] = {}
    for event in ctx.telemetry.snapshot_events(2000):
        for control in event.get("controls_fired") or []:
            hits[control] = hits.get(control, 0) + 1
            last.setdefault(control, event.get("ts") or "")
    out = []
    for spec in described["controls"]:
        out.append({**spec, "hits": hits.get(spec["id"], 0), "last_hit": last.get(spec["id"])})
    return out


__all__ = ["GateContext", "execute_gated_scan", "control_catalog_with_hits", "CONTROL_BY_ID"]
