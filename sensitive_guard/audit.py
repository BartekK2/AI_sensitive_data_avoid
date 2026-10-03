"""Append-only audit trail for security teams (JSONL, exportable as CSV)."""

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "audit.jsonl"

EXPORT_COLUMNS = [
    "ts",
    "request_id",
    "direction",
    "action",
    "risk",
    "kind",
    "employee_id",
    "employee_name",
    "team",
    "role_name",
    "destination",
    "model",
    "categories",
    "labels",
    "controls_fired",
    "backend",
    "latency_ms",
    "tokens_est",
    "policy_version",
    "incident_id",
    "excerpt",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mask_value(value: str) -> str:
    """Keep the shape of a secret or identifier without the content."""
    if not value:
        return ""
    compact = value.strip()
    if len(compact) <= 4:
        return "*" * len(compact)
    return compact[:2] + "*" * max(3, len(compact) - 4) + compact[-2:]


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        row = {"ts": _now(), **event}
        with self._lock:
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return row

    def tail(self, limit: int = 2000) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def query(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        action: str | None = None,
        kind: str | None = None,
        employee: str | None = None,
        team: str | None = None,
        destination: str | None = None,
        direction: str | None = None,
        q: str | None = None,
        limit: int = 500,
        reveal: bool = False,
    ) -> list[dict[str, Any]]:
        rows = self.tail(limit=max(limit * 4, 2000))
        out: list[dict[str, Any]] = []
        needle = (q or "").lower()
        for row in reversed(rows):
            if since and row.get("ts", "") < since:
                continue
            if until and row.get("ts", "") > until:
                continue
            if action and row.get("action") != action:
                continue
            if kind and row.get("kind") != kind:
                continue
            if direction and row.get("direction") != direction:
                continue
            if employee and employee not in {row.get("employee_id"), row.get("employee_name")}:
                continue
            if team and row.get("team") != team:
                continue
            if destination and destination.lower() not in (row.get("destination") or "").lower():
                continue
            if needle:
                blob = json.dumps(row, ensure_ascii=False).lower()
                if needle not in blob:
                    continue
            out.append(row if reveal else self.redact_row(row))
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def redact_row(row: dict[str, Any]) -> dict[str, Any]:
        safe = dict(row)
        safe.pop("raw_values", None)
        return safe

    @staticmethod
    def to_csv(rows: Iterable[dict[str, Any]]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for key in ("categories", "labels", "controls_fired"):
                value = flat.get(key)
                if isinstance(value, list):
                    flat[key] = "|".join(str(item) for item in value)
            writer.writerow(flat)
        return buffer.getvalue()

    @staticmethod
    def to_jsonl(rows: Iterable[dict[str, Any]]) -> str:
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.write_text("", encoding="utf-8")
            except OSError:
                pass
