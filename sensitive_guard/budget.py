"""Token / cost budgets and request rate limits per employee, team and model."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from .policy import BudgetConfig


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(math.ceil(len(text) / 4.0)))


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class BudgetTracker:
    """Usage counters persisted in workspace.json under `usage`; RPM kept in memory."""

    def __init__(self, store) -> None:
        self.store = store
        self._lock = threading.Lock()
        self._rpm: dict[str, deque[float]] = {}

    def _usage(self, data: dict[str, Any]) -> dict[str, Any]:
        usage = data.get("usage")
        if not isinstance(usage, dict) or usage.get("date") != _today():
            usage = {"date": _today(), "employees": {}, "teams": {}, "models": {}}
            data["usage"] = usage
        for key in ("employees", "teams", "models"):
            usage.setdefault(key, {})
        return usage

    @staticmethod
    def _bucket(table: dict[str, Any], key: str) -> dict[str, Any]:
        row = table.get(key)
        if not isinstance(row, dict):
            row = {"tokens": 0, "requests": 0, "cost": 0.0, "blocked": 0}
            table[key] = row
        return row

    def cost_for(self, config: BudgetConfig, model: str | None, tokens: int) -> float:
        if not model:
            return 0.0
        name = model.lower()
        for known, rate in config.cost_per_1k.items():
            if name == known.lower() or name.startswith(known.lower()):
                return round(rate * tokens / 1000.0, 6)
        return 0.0

    def is_local_model(self, config: BudgetConfig, model: str | None) -> bool:
        if not model:
            return False
        name = model.lower()
        return any(name.startswith(local.lower()) for local in config.local_models)

    def limit_for(self, config: BudgetConfig, scope: str, key: str) -> int:
        table = getattr(config.limits, scope)
        if key in table:
            return int(table[key])
        if scope == "employees":
            return config.default_tokens_per_day
        if scope == "teams":
            return config.default_team_tokens_per_day
        return config.default_model_tokens_per_day

    def check_rate(self, config: BudgetConfig, employee_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            window = self._rpm.setdefault(employee_key, deque())
            while window and now - window[0] > 60.0:
                window.popleft()
            count = len(window)
            if config.requests_per_min and count >= config.requests_per_min:
                return False, count
            window.append(now)
            return True, count + 1

    def check(
        self,
        config: BudgetConfig,
        *,
        employee: dict[str, Any] | None,
        model: str | None,
        tokens: int,
    ) -> dict[str, Any]:
        """Return {allowed, reason, scope, pct, warnings} without consuming."""
        if not config.enabled:
            return {"allowed": True, "reason": None, "warnings": [], "pct": 0}
        data = self.store.snapshot()
        usage = self._usage(data)
        checks: list[tuple[str, str]] = []
        if employee and employee.get("id"):
            checks.append(("employees", employee["id"]))
        if employee and employee.get("team"):
            checks.append(("teams", employee["team"]))
        if model:
            checks.append(("models", model))
        warnings: list[dict[str, Any]] = []
        worst_pct = 0
        for scope, key in checks:
            limit = self.limit_for(config, scope, key)
            if limit <= 0:
                continue
            used = int(self._bucket(usage[scope], key).get("tokens") or 0)
            pct = int(round(100.0 * (used + tokens) / limit))
            worst_pct = max(worst_pct, pct)
            if used + tokens > limit:
                return {
                    "allowed": False,
                    "reason": f"{scope[:-1]} budget exceeded: {key} ({used + tokens}/{limit} tokens)",
                    "scope": scope,
                    "key": key,
                    "pct": pct,
                    "warnings": warnings,
                }
            if pct >= config.alert_pct:
                warnings.append({"scope": scope, "key": key, "pct": pct, "limit": limit, "used": used + tokens})
        return {"allowed": True, "reason": None, "pct": worst_pct, "warnings": warnings}

    def consume(
        self,
        config: BudgetConfig,
        *,
        employee: dict[str, Any] | None,
        model: str | None,
        tokens: int,
        blocked: bool = False,
        budget_hit: tuple[str, str] | None = None,
    ) -> None:
        """Record a request. ``budget_hit`` = (scope, key) whose limit stopped it."""
        cost = self.cost_for(config, model, tokens)

        def mutate(data: dict[str, Any]) -> None:
            usage = self._usage(data)
            targets: list[tuple[str, str]] = []
            if employee and employee.get("id"):
                targets.append(("employees", employee["id"]))
            if employee and employee.get("team"):
                targets.append(("teams", employee["team"]))
            if model:
                targets.append(("models", model))
            if not employee:
                targets.append(("employees", "unknown"))
            for scope, key in targets:
                row = self._bucket(usage[scope], key)
                row["requests"] = int(row.get("requests") or 0) + 1
                if blocked:
                    row["blocked"] = int(row.get("blocked") or 0) + 1
                    if budget_hit == (scope, key):
                        row["budget_blocks"] = int(row.get("budget_blocks") or 0) + 1
                else:
                    row["tokens"] = int(row.get("tokens") or 0) + tokens
                    row["cost"] = round(float(row.get("cost") or 0.0) + cost, 6)
                if scope == "models":
                    row["local"] = self.is_local_model(config, key)

        self.store.update(mutate)

    def summary(self, config: BudgetConfig) -> dict[str, Any]:
        data = self.store.snapshot()
        usage = self._usage(data)
        employees = {item.get("id"): item for item in data.get("employees", [])}
        out: dict[str, Any] = {"date": usage.get("date"), "enabled": config.enabled, "alert_pct": config.alert_pct,
                               "requests_per_min": config.requests_per_min, "exceeded": [], "warnings": [],
                               "employees": [], "teams": [], "models": [], "totals": {"tokens": 0, "cost": 0.0, "requests": 0, "blocked": 0}}
        for scope in ("employees", "teams", "models"):
            rows = []
            keys = set(usage[scope]) | set(getattr(config.limits, scope))
            if scope == "employees":
                keys |= set(employees)
            for key in sorted(keys):
                row = usage[scope].get(key) or {}
                limit = self.limit_for(config, scope, key)
                used = int(row.get("tokens") or 0)
                pct = int(round(100.0 * used / limit)) if limit else 0
                label = key
                team = None
                if scope == "employees" and key in employees:
                    label = employees[key].get("name") or key
                    team = employees[key].get("team")
                entry = {
                    "key": key,
                    "label": label,
                    "team": team,
                    "tokens": used,
                    "requests": int(row.get("requests") or 0),
                    "blocked": int(row.get("blocked") or 0),
                    "cost": round(float(row.get("cost") or 0.0), 4),
                    "limit": limit,
                    "pct": pct,
                    "remaining": max(0, limit - used),
                    "local": bool(row.get("local")) if scope == "models" else None,
                    "budget_blocks": int(row.get("budget_blocks") or 0),
                }
                # A limit that already stopped a request counts as exceeded even if the
                # consumed tokens sit just below it (blocked requests do not consume).
                if pct >= 100 or entry["budget_blocks"] > 0:
                    out["exceeded"].append(f"{scope[:-1]}:{key}")
                elif pct >= config.alert_pct:
                    out["warnings"].append({"scope": scope, "key": key, "label": label, "pct": pct})
                rows.append(entry)
                if scope == "employees":
                    out["totals"]["tokens"] += used
                    out["totals"]["cost"] += entry["cost"]
                    out["totals"]["requests"] += entry["requests"]
                    out["totals"]["blocked"] += entry["blocked"]
            rows.sort(key=lambda item: -item["tokens"])
            out[scope] = rows
        out["totals"]["cost"] = round(out["totals"]["cost"], 4)
        local_tokens = sum(item["tokens"] for item in out["models"] if item.get("local"))
        cloud_tokens = sum(item["tokens"] for item in out["models"] if not item.get("local"))
        out["split"] = {"local": local_tokens, "cloud": cloud_tokens}
        return out

    def reset(self) -> None:
        def mutate(data: dict[str, Any]) -> None:
            data["usage"] = {"date": _today(), "employees": {}, "teams": {}, "models": {}}

        self.store.update(mutate)
        with self._lock:
            self._rpm.clear()
