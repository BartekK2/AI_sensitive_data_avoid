"""Centralized control policy: one JSON file the judges can edit at runtime.

`data/policy.json` holds thresholds, per-category actions, allowed models,
budgets, the control catalog and agent guardrails. It is re-read whenever its
mtime changes, so edits on disk are reflected on the next request.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .taxonomy import ACTION_ORDER, GateAction, RiskLevel, action_for_risk

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "policy.json"

DETERMINISTIC = "deterministic"
SEMANTIC = "semantic"

# label -> control id. Labels not listed belong to the PII classifier control.
LABEL_CONTROL: dict[str, str] = {
    "pesel": "pesel_checksum",
    "social security number": "pesel_checksum",
    "nip": "nip_checksum",
    "tax number": "nip_checksum",
    "regon": "regon_checksum",
    "iban": "iban_check",
    "credit card number": "luhn_card",
    "api key": "secrets_regex",
    "access token": "secrets_regex",
    "private key": "secrets_regex",
    "password": "secrets_regex",
}

CONTROL_CATALOG: list[dict[str, Any]] = [
    {"id": "pesel_checksum", "type": DETERMINISTIC, "label": "PESEL / SSN checksum", "critical": True,
     "description": "Validates Polish national IDs by checksum; survives a 'not pii' vote from the model."},
    {"id": "nip_checksum", "type": DETERMINISTIC, "label": "NIP / tax number checksum", "critical": False,
     "description": "Weighted checksum for Polish tax IDs."},
    {"id": "regon_checksum", "type": DETERMINISTIC, "label": "REGON checksum", "critical": False,
     "description": "Company registry identifier validation."},
    {"id": "iban_check", "type": DETERMINISTIC, "label": "IBAN mod-97", "critical": True,
     "description": "Bank account numbers validated with ISO 13616 mod-97."},
    {"id": "luhn_card", "type": DETERMINISTIC, "label": "Payment card (Luhn)", "critical": True,
     "description": "Card numbers validated with the Luhn algorithm (PCI-DSS)."},
    {"id": "secrets_regex", "type": DETERMINISTIC, "label": "Secrets and API keys", "critical": True,
     "description": "Provider key prefixes, bearer tokens, PEM blocks, password= assignments."},
    {"id": "pii_classifier", "type": SEMANTIC, "label": "PII span classifier (Laya / heuristic)", "critical": False,
     "description": "22-label Laya Experts PII head, or the rule heuristic when weights are not loaded."},
    {"id": "laya_policy", "type": SEMANTIC, "label": "Laya document policy", "critical": False,
     "description": "Document-level allow / redact / block vote (100+ languages). Needs --policy."},
    {"id": "custom_patterns", "type": DETERMINISTIC, "label": "Custom category patterns", "critical": False,
     "description": "Regex patterns attached to workspace categories (e.g. health, project codenames)."},
    {"id": "signatures", "type": DETERMINISTIC, "label": "Attack signatures feed", "critical": True,
     "description": "Prompt injection, jailbreak, unsafe deserialization, malicious code, supply chain."},
    {"id": "model_allowlist", "type": DETERMINISTIC, "label": "Allowed LLM models", "critical": False,
     "description": "Requests naming a model outside the allow-list are refused."},
    {"id": "budget", "type": DETERMINISTIC, "label": "Token and cost budget", "critical": False,
     "description": "Daily token budgets per employee, team and model."},
    {"id": "rate_limit", "type": DETERMINISTIC, "label": "Requests per minute", "critical": False,
     "description": "Per-employee request rate ceiling."},
    {"id": "loop_guard", "type": DETERMINISTIC, "label": "Agent loop guard", "critical": False,
     "description": "Same prompt repeated N times in a short window is a runaway agent."},
    {"id": "tool_allowlist", "type": DETERMINISTIC, "label": "Agent tool allow-list", "critical": False,
     "description": "Function / tool calls outside the list are stripped or refused."},
    {"id": "memory_isolation", "type": DETERMINISTIC, "label": "Memory isolation", "critical": False,
     "description": "Prompt carrying another employee's identity context is refused."},
    {"id": "output_scan", "type": SEMANTIC, "label": "Response scanning", "critical": False,
     "description": "Model output is scanned and redacted before it reaches the caller."},
    {"id": "whitelist", "type": DETERMINISTIC, "label": "Whitelist exceptions", "critical": False,
     "description": "Company domains, helpdesk addresses and test identifiers are not leaks."},
    {"id": "roles", "type": DETERMINISTIC, "label": "Role exceptions", "critical": False,
     "description": "HR may send names and phones; Finance may send IBANs."},
]

CONTROL_IDS = [item["id"] for item in CONTROL_CATALOG]
CONTROL_BY_ID = {item["id"]: item for item in CONTROL_CATALOG}

PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "threshold": 0.35,
        "strict": True,
        "category_actions": {
            "government_id": "block",
            "financial": "block",
            "credentials": "block",
            "attack": "block",
            "contact": "block",
            "person_name": "redact",
            "location": "redact",
            "demographic": "redact",
            "temporal": "redact",
            "online": "redact",
            "health": "block",
        },
    },
    "balanced": {
        "threshold": 0.5,
        "strict": False,
        "category_actions": {
            "government_id": "block",
            "financial": "block",
            "credentials": "block",
            "attack": "block",
            "health": "redact",
        },
    },
    "permissive": {
        "threshold": 0.7,
        "strict": False,
        "category_actions": {
            "government_id": "block",
            "financial": "block",
            "credentials": "block",
            "attack": "block",
            "contact": "allow",
            "person_name": "allow",
            "location": "allow",
            "demographic": "allow",
            "temporal": "allow",
            "online": "allow",
        },
    },
}


class ControlState(BaseModel):
    enabled: bool = True
    threshold: float | None = None


class BudgetLimits(BaseModel):
    employees: dict[str, int] = Field(default_factory=dict)
    teams: dict[str, int] = Field(default_factory=dict)
    models: dict[str, int] = Field(default_factory=dict)


class BudgetConfig(BaseModel):
    enabled: bool = True
    alert_pct: int = 80
    default_tokens_per_day: int = 20000
    default_team_tokens_per_day: int = 60000
    default_model_tokens_per_day: int = 200000
    requests_per_min: int = 30
    # PLN per 1k tokens. Local models are free, cloud models use list prices.
    cost_per_1k: dict[str, float] = Field(
        default_factory=lambda: {
            "gpt-4o-mini": 0.0024,
            "gpt-4o": 0.02,
            "claude-3-5-sonnet": 0.012,
            "gemini-2.5-flash": 0.0012,
            "gemini-3.5-flash-lite": 0.0008,
            "llama3": 0.0,
            "ollama": 0.0,
        }
    )
    local_models: list[str] = Field(default_factory=lambda: ["llama3", "ollama", "mistral-local", "qwen"])
    limits: BudgetLimits = Field(default_factory=BudgetLimits)


class AgentGuards(BaseModel):
    loop_window_s: int = 60
    loop_max_repeats: int = 5
    allowed_tools: list[str] | None = None
    memory_isolation: bool = True


class Policy(BaseModel):
    version: int = 1
    updated_at: str = ""
    updated_by: str = "seed"
    preset: str = "balanced"
    threshold: float = 0.5
    strict: bool = False
    category_actions: dict[str, str] = Field(default_factory=lambda: dict(PRESETS["balanced"]["category_actions"]))
    destination_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)
    allowed_models: list[str] = Field(default_factory=list)
    scan_output: bool = True
    controls: dict[str, ControlState] = Field(default_factory=lambda: {cid: ControlState() for cid in CONTROL_IDS})
    budgets: BudgetConfig = Field(default_factory=BudgetConfig)
    agent: AgentGuards = Field(default_factory=AgentGuards)
    signatures_path: str = "signatures.json"

    def control_enabled(self, control_id: str) -> bool:
        state = self.controls.get(control_id)
        return True if state is None else state.enabled

    def disabled_controls(self) -> list[str]:
        return [cid for cid in CONTROL_IDS if not self.control_enabled(cid)]

    def effective_actions(self, destination: str | None = None) -> dict[str, str]:
        merged = dict(self.category_actions)
        dest = (destination or "").lower()
        for needle, overrides in self.destination_overrides.items():
            if needle and needle.lower() in dest:
                merged.update(overrides)
        return merged

    def action_for(self, category: str, risk: str, destination: str | None = None) -> GateAction:
        overrides = self.effective_actions(destination)
        forced = overrides.get(category)
        if forced:
            try:
                return GateAction(forced)
            except ValueError:
                pass
        try:
            level = RiskLevel(risk)
        except ValueError:
            level = RiskLevel.MEDIUM
        return action_for_risk(level, strict=self.strict)

    def model_allowed(self, model: str | None) -> bool:
        if not model or not self.allowed_models or not self.control_enabled("model_allowlist"):
            return True
        wanted = model.lower()
        for allowed in self.allowed_models:
            pattern = allowed.lower()
            if pattern == wanted or (pattern.endswith("*") and wanted.startswith(pattern[:-1])):
                return True
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seed_policy() -> Policy:
    policy = Policy(updated_at=_now())
    policy.allowed_models = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1*",
        "claude-3*",
        "claude-sonnet*",
        "gemini-*",
        "llama3*",
        "mistral*",
        "qwen*",
    ]
    policy.destination_overrides = {
        "openai": {"person_name": "redact"},
        "chatgpt.com": {"contact": "redact"},
        "localhost": {"contact": "allow", "person_name": "allow"},
    }
    policy.budgets.limits.employees = {"emp_anna": 8000, "emp_piotr": 12000}
    policy.budgets.limits.teams = {"Support": 30000, "Sprzedaż": 40000}
    policy.budgets.limits.models = {"gpt-4o": 50000}
    return policy


def apply_preset(policy: Policy, name: str) -> Policy:
    preset = PRESETS.get(name)
    if preset is None:
        raise KeyError(name)
    data = policy.model_dump()
    data["preset"] = name
    data["threshold"] = preset["threshold"]
    data["strict"] = preset["strict"]
    data["category_actions"] = dict(preset["category_actions"])
    return Policy.model_validate(data)


class PolicyStore:
    """Load / save the policy with mtime-based hot reload and a change history."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self.history_path = self.path.with_name(self.path.stem + "_history.jsonl")
        self._lock = threading.Lock()
        self._cached: Policy | None = None
        self._mtime: float | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(seed_policy())

    def _write(self, policy: Policy) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(policy.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def mtime(self) -> float:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return 0.0

    def load(self) -> Policy:
        with self._lock:
            current = self.mtime()
            if self._cached is not None and current == self._mtime:
                return self._cached
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                policy = Policy.model_validate(data)
            except (OSError, ValueError) as error:
                if self._cached is not None:
                    return self._cached
                policy = seed_policy()
                self._append_history({"ts": _now(), "actor": "system", "change": f"invalid policy file: {error}; seeded"})
            if self._cached is not None and self._mtime is not None and current != self._mtime:
                self._append_history({
                    "ts": _now(),
                    "actor": "disk",
                    "change": "policy file changed on disk",
                    "version": policy.version,
                })
            self._cached = policy
            self._mtime = current
            return policy

    def save(self, policy: Policy, *, actor: str = "dashboard", change: str = "policy updated") -> Policy:
        with self._lock:
            policy.version = (self._cached.version if self._cached else policy.version) + 1
            policy.updated_at = _now()
            policy.updated_by = actor
            self._write(policy)
            self._cached = policy
            self._mtime = self.mtime()
            self._append_history({"ts": policy.updated_at, "actor": actor, "change": change, "version": policy.version})
            return policy

    def update(self, patch: dict[str, Any], *, actor: str = "dashboard", change: str | None = None) -> Policy:
        current = self.load().model_dump()
        current.update(patch)
        policy = Policy.model_validate(current)
        return self.save(policy, actor=actor, change=change or f"updated {', '.join(sorted(patch))}")

    def set_control(self, control_id: str, *, enabled: bool | None = None, threshold: float | None = None, actor: str = "dashboard") -> Policy:
        if control_id not in CONTROL_BY_ID:
            raise KeyError(control_id)
        policy = self.load()
        state = policy.controls.get(control_id) or ControlState()
        if enabled is not None:
            state.enabled = enabled
        if threshold is not None:
            state.threshold = threshold
        policy.controls[control_id] = state
        verb = "enabled" if state.enabled else "disabled"
        return self.save(policy, actor=actor, change=f"control {control_id} {verb}")

    def use_preset(self, name: str, *, actor: str = "dashboard") -> Policy:
        policy = apply_preset(self.load(), name)
        return self.save(policy, actor=actor, change=f"preset {name}")

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows[-limit:][::-1]

    def _append_history(self, row: dict[str, Any]) -> None:
        try:
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def describe(self) -> dict[str, Any]:
        policy = self.load()
        catalog = []
        for spec in CONTROL_CATALOG:
            state = policy.controls.get(spec["id"]) or ControlState()
            catalog.append({**spec, "enabled": state.enabled, "threshold": state.threshold})
        return {
            "policy": policy.model_dump(),
            "controls": catalog,
            "presets": list(PRESETS),
            "path": str(self.path),
            "mtime": self.mtime(),
            "disabled_critical": [
                cid for cid in policy.disabled_controls() if CONTROL_BY_ID[cid].get("critical")
            ],
        }


def strongest(actions: list[GateAction]) -> GateAction:
    if not actions:
        return GateAction.ALLOW
    return max(actions, key=lambda item: ACTION_ORDER[item])
