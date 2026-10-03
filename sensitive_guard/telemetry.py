"""In-process telemetry: decisions ring buffer, latency percentiles, posture score."""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from typing import Any

RING_SIZE = 2000


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return float(ordered[index])


class Telemetry:
    def __init__(self, size: int = RING_SIZE) -> None:
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc)
        self.events: deque[dict[str, Any]] = deque(maxlen=size)
        self.counters: Counter[str] = Counter()
        self.last_test_run: dict[str, Any] | None = None

    def record(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.events.append(event)
            action = event.get("action") or "allow"
            self.counters[f"action:{action}"] += 1
            kind = event.get("kind") or "pii"
            if action != "allow":
                self.counters[f"kind:{kind}"] += 1
            if event.get("backend"):
                self.counters[f"backend:{event['backend']}"] += 1
            if event.get("direction") == "output" and action != "allow":
                self.counters["output_redactions"] += 1

    def bump(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[name] += amount

    def hydrate(self, rows: list[dict[str, Any]]) -> None:
        """Seed the ring buffer from the persisted audit trail at start-up."""
        for row in rows[-RING_SIZE:]:
            self.record(row)

    def snapshot_events(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.events)[-limit:][::-1]

    def metrics(self, *, incidents: list[dict[str, Any]], policy_summary: dict[str, Any], budget_summary: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self._lock:
            events = list(self.events)
            counters = dict(self.counters)
        today = now.date().isoformat()
        minute_ago = now - timedelta(seconds=60)
        fifteen_ago = now - timedelta(minutes=15)
        day_ago = now - timedelta(hours=24)

        hourly = [{"hour": (now - timedelta(hours=23 - index)).strftime("%H:00"), "block": 0, "redact": 0, "allow": 0} for index in range(24)]
        minutes = [{"minute": (now - timedelta(minutes=14 - index)).strftime("%H:%M"), "count": 0} for index in range(15)]
        per_team: Counter[str] = Counter()
        per_destination: Counter[str] = Counter()
        per_category: Counter[str] = Counter()
        per_kind: Counter[str] = Counter()
        per_employee: Counter[str] = Counter()
        employee_names: dict[str, str] = {}
        today_counts = Counter()
        latencies: list[float] = []
        rpm = 0
        backend: Counter[str] = Counter()
        tokens_today = 0

        for event in events:
            ts = _parse_ts(event.get("ts"))
            action = event.get("action") or "allow"
            if event.get("latency_ms") is not None:
                latencies.append(float(event["latency_ms"]))
            if event.get("backend"):
                backend[event["backend"]] += 1
            if ts is None:
                continue
            if ts >= minute_ago:
                rpm += 1
            if ts.date().isoformat() == today:
                today_counts[action] += 1
                tokens_today += int(event.get("tokens_est") or 0)
            if ts >= day_ago:
                offset = 23 - int((now - ts).total_seconds() // 3600)
                if 0 <= offset < 24 and action in {"block", "redact", "allow"}:
                    hourly[offset][action] += 1
            if ts >= fifteen_ago and action != "allow":
                offset = 14 - int((now - ts).total_seconds() // 60)
                if 0 <= offset < 15:
                    minutes[offset]["count"] += 1
            if action != "allow":
                per_team[event.get("team") or "—"] += 1
                per_destination[event.get("destination") or "—"] += 1
                per_kind[event.get("kind") or "pii"] += 1
                for category in event.get("categories") or []:
                    per_category[category] += 1
                emp = event.get("employee_id") or event.get("employee_name") or "unknown"
                per_employee[emp] += 1
                employee_names[emp] = event.get("employee_name") or emp

        open_incidents = [item for item in incidents if item.get("status") == "open"]
        open_critical = [item for item in open_incidents if item.get("risk") == "critical"]
        open_attacks = [item for item in open_incidents if item.get("kind") == "attack"]
        oldest_open = None
        for item in open_incidents:
            ts = _parse_ts(item.get("created_at"))
            if ts and (oldest_open is None or ts < oldest_open):
                oldest_open = ts

        score = 100
        deductions: list[dict[str, Any]] = []

        def deduct(points: int, reason: str) -> None:
            nonlocal score
            if points <= 0:
                return
            score -= points
            deductions.append({"points": points, "reason": reason})

        deduct(min(45, 15 * len(open_critical)), f"{len(open_critical)} open critical incident(s)")
        deduct(min(20, 5 * len(open_attacks)), f"{len(open_attacks)} open attack incident(s)")
        disabled_critical = policy_summary.get("disabled_critical") or []
        deduct(10 * len(disabled_critical), f"critical controls disabled: {', '.join(disabled_critical)}")
        exceeded = budget_summary.get("exceeded") or []
        deduct(10 if exceeded else 0, f"budget exceeded: {', '.join(exceeded[:3])}")
        deduct(10 if health.get("backend") == "heuristic" else 0, "semantic model not loaded (regex-only mode)")
        deduct(5 if not policy_summary.get("signatures_enabled", True) else 0, "attack signatures disabled")
        score = max(0, score)

        top_people = [
            {"employee_id": emp, "employee_name": employee_names.get(emp, emp), "count": count}
            for emp, count in per_employee.most_common(5)
        ]

        return {
            "generated_at": now.isoformat(timespec="seconds"),
            "uptime_s": int((now - self.started_at).total_seconds()),
            "posture": {"score": score, "deductions": deductions},
            "today": {
                "block": today_counts.get("block", 0),
                "redact": today_counts.get("redact", 0),
                "allow": today_counts.get("allow", 0),
                "total": sum(today_counts.values()),
                "tokens": tokens_today,
            },
            "totals": {
                "block": counters.get("action:block", 0),
                "redact": counters.get("action:redact", 0),
                "allow": counters.get("action:allow", 0),
                "attacks": counters.get("kind:attack", 0),
                "budget_blocks": counters.get("kind:budget", 0),
                "model_blocks": counters.get("kind:model", 0),
                "loop_blocks": counters.get("kind:loop", 0),
                "memory_blocks": counters.get("kind:memory", 0),
                "tool_blocks": counters.get("kind:tool", 0),
                "rate_limited": counters.get("kind:rate_limit", 0),
                "output_redactions": counters.get("output_redactions", 0),
                "upstream_errors": counters.get("upstream_errors", 0),
                "upstream_timeouts": counters.get("upstream_timeouts", 0),
            },
            "incidents": {
                "open": len(open_incidents),
                "open_critical": len(open_critical),
                "open_attacks": len(open_attacks),
                "total": len(incidents),
                "oldest_open_at": oldest_open.isoformat(timespec="seconds") if oldest_open else None,
            },
            "hourly": hourly,
            "last_15_min": minutes,
            "per_team": [{"team": key, "count": value} for key, value in per_team.most_common(12)],
            "per_destination": [{"destination": key, "count": value} for key, value in per_destination.most_common(12)],
            "per_category": [{"category": key, "count": value} for key, value in per_category.most_common(12)],
            "per_kind": [{"kind": key, "count": value} for key, value in per_kind.most_common()],
            "top_people": top_people,
            "latency_ms": {
                "last": latencies[-1] if latencies else 0.0,
                "avg": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
                "p50": round(percentile(latencies, 50), 1),
                "p95": round(percentile(latencies, 95), 1),
                "samples": len(latencies),
            },
            "rpm": rpm,
            "backend_split": dict(backend),
            "ring_size": len(events),
            "tests_last_run": self.last_test_run,
        }


class Stopwatch:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self.start) * 1000.0, 2)
