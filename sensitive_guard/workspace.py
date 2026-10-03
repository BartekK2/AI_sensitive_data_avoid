"""JSON workspace: people, roles, categories, whitelist, incidents."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .taxonomy import RiskLevel, max_risk

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "workspace.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def seed() -> dict[str, Any]:
    return {
        "roles": [
            {
                "id": "role_pracownik",
                "name": "Pracownik",
                "level": "standard",
                "allowed_categories": [],
                "can_override": False,
                "description": "Brak wyjątków — każda wycieczka PII ląduje u managera.",
            },
            {
                "id": "role_hr",
                "name": "HR",
                "level": "elevated",
                "allowed_categories": ["person_name", "contact", "demographic"],
                "can_override": False,
                "description": "Może podawać imiona i telefony w rekrutacji.",
            },
            {
                "id": "role_finanse",
                "name": "Finanse",
                "level": "elevated",
                "allowed_categories": ["financial"],
                "can_override": False,
                "description": "IBAN i karty testowe firmy nie są incydentem.",
            },
            {
                "id": "role_manager",
                "name": "Manager",
                "level": "admin",
                "allowed_categories": ["*"],
                "can_override": True,
                "description": "Widzi dashboard i może nadpisywać blokady.",
            },
        ],
        "employees": [
            {
                "id": "emp_anna",
                "name": "Anna Nowak",
                "email": "anna.nowak@helios.pl",
                "role_id": "role_pracownik",
                "team": "Support",
            },
            {
                "id": "emp_piotr",
                "name": "Piotr Zieliński",
                "email": "piotr.zielinski@helios.pl",
                "role_id": "role_pracownik",
                "team": "Sprzedaż",
            },
            {
                "id": "emp_magda",
                "name": "Magda Lewandowska",
                "email": "magda.lewandowska@helios.pl",
                "role_id": "role_hr",
                "team": "HR",
            },
            {
                "id": "emp_tomasz",
                "name": "Tomasz Bąk",
                "email": "tomasz.bak@helios.pl",
                "role_id": "role_finanse",
                "team": "Finanse",
            },
            {
                "id": "emp_kasia",
                "name": "Katarzyna Wójcik",
                "email": "kasia.wojcik@helios.pl",
                "role_id": "role_manager",
                "team": "Operacje",
            },
        ],
        "categories": [
            {"id": "cat_gov", "key": "government_id", "label": "Identyfikatory (PESEL, NIP)", "risk": "critical", "enabled": True, "builtin": True},
            {"id": "cat_fin", "key": "financial", "label": "Finanse (karta, IBAN)", "risk": "critical", "enabled": True, "builtin": True},
            {"id": "cat_cred", "key": "credentials", "label": "Sekrety i klucze", "risk": "critical", "enabled": True, "builtin": True},
            {"id": "cat_contact", "key": "contact", "label": "Kontakt (e-mail, telefon)", "risk": "medium", "enabled": True, "builtin": True},
            {"id": "cat_name", "key": "person_name", "label": "Dane osobowe — imię", "risk": "medium", "enabled": True, "builtin": True},
            {"id": "cat_loc", "key": "location", "label": "Lokalizacja", "risk": "medium", "enabled": True, "builtin": True},
            {"id": "cat_demo", "key": "demographic", "label": "Demografia", "risk": "low", "enabled": True, "builtin": True},
        ],
        "whitelist": [
            {
                "id": "wl_domain",
                "type": "domain",
                "value": "helios.pl",
                "reason": "Firmowa domena — adresy wewnętrzne OK",
                "enabled": True,
            },
            {
                "id": "wl_nip",
                "type": "pattern",
                "value": "5252341111",
                "reason": "NIP spółki Helios",
                "enabled": True,
            },
            {
                "id": "wl_help",
                "type": "email",
                "value": "pomoc@helios.pl",
                "reason": "Publiczny adres helpdesku",
                "enabled": True,
            },
        ],
        "incidents": [
            {
                "id": "inc_seed1",
                "created_at": "2026-10-03T09:14:00+00:00",
                "employee_id": "emp_anna",
                "employee_name": "Anna Nowak",
                "role_name": "Pracownik",
                "team": "Support",
                "destination": "chatgpt.com",
                "action": "block",
                "risk": "critical",
                "categories": ["government_id"],
                "labels": ["pesel"],
                "redacted": "Klient ma PESEL [PESEL], proszę sprawdzić polisę.",
                "status": "open",
                "note": "",
                "kind": "pii",
                "count": 1,
                "controls_fired": ["pesel_checksum"],
                "demo": True,
            },
            {
                "id": "inc_seed2",
                "created_at": "2026-10-03T10:02:00+00:00",
                "employee_id": "emp_piotr",
                "employee_name": "Piotr Zieliński",
                "role_name": "Pracownik",
                "team": "Sprzedaż",
                "destination": "claude.ai",
                "action": "redact",
                "risk": "medium",
                "categories": ["contact"],
                "labels": ["email address", "phone number"],
                "redacted": "Oddzwoń do [EMAIL] albo [TELEFON].",
                "status": "open",
                "note": "",
                "kind": "pii",
                "count": 1,
                "controls_fired": ["pii_classifier"],
                "demo": True,
            },
            {
                "id": "inc_seed3",
                "created_at": "2026-10-02T16:40:00+00:00",
                "employee_id": "emp_tomasz",
                "employee_name": "Tomasz Bąk",
                "role_name": "Finanse",
                "team": "Finanse",
                "destination": "gemini.google.com",
                "action": "block",
                "risk": "critical",
                "categories": ["credentials"],
                "labels": ["api key"],
                "redacted": "Klucz testowy: [KLUCZ API]",
                "status": "ack",
                "note": "Klucz unieważniony.",
                "kind": "pii",
                "count": 1,
                "controls_fired": ["secrets_regex"],
                "demo": True,
            },
        ],
    }


class WorkspaceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(seed())

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._read()

    def update(self, mutator) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            mutator(data)
            self._write(data)
            return data

    def list_collection(self, name: str) -> list[dict[str, Any]]:
        return list(self.snapshot().get(name, []))

    def upsert(self, name: str, item: dict[str, Any], prefix: str) -> dict[str, Any]:
        if not item.get("id"):
            item["id"] = _id(prefix)

        def mutate(data: dict[str, Any]) -> None:
            rows = data.setdefault(name, [])
            for index, row in enumerate(rows):
                if row.get("id") == item["id"]:
                    rows[index] = {**row, **item}
                    return
            rows.append(item)

        self.update(mutate)
        return item

    def delete(self, name: str, item_id: str) -> bool:
        found = False

        def mutate(data: dict[str, Any]) -> None:
            nonlocal found
            rows = data.get(name, [])
            kept = [row for row in rows if row.get("id") != item_id]
            found = len(kept) != len(rows)
            data[name] = kept

        self.update(mutate)
        return found

    def employee_by_id_or_email(self, employee_id: str | None, email: str | None) -> dict[str, Any] | None:
        data = self.snapshot()
        for employee in data.get("employees", []):
            if employee_id and employee.get("id") == employee_id:
                return employee
            if email and employee.get("email", "").lower() == email.lower():
                return employee
        return None

    def role_for(self, employee: dict[str, Any] | None) -> dict[str, Any] | None:
        if not employee:
            return None
        for role in self.snapshot().get("roles", []):
            if role.get("id") == employee.get("role_id"):
                return role
        return None


def entity_whitelisted(entity: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = (entity.get("text") or "").strip()
    label = entity.get("label") or ""
    category = entity.get("category") or ""
    compact = re.sub(r"[\s-]+", "", text)
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        kind = rule.get("type")
        value = (rule.get("value") or "").strip()
        if not value:
            continue
        if kind == "label" and value in {label, category}:
            return rule
        if kind == "email" and value.lower() == text.lower():
            return rule
        if kind == "domain":
            domain = value.lower().lstrip("@")
            if text.lower().endswith("@" + domain) or domain in text.lower():
                return rule
        if kind == "pattern":
            needle = re.sub(r"[\s-]+", "", value)
            if value.lower() in text.lower() or needle in compact:
                return rule
    return None


def role_allows(role: dict[str, Any] | None, category: str) -> bool:
    if not role:
        return False
    allowed = role.get("allowed_categories") or []
    return "*" in allowed or category in allowed


def apply_workspace_policy(
    entities: list[dict[str, Any]],
    *,
    store: WorkspaceStore,
    employee: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    role = store.role_for(employee)
    rules = store.list_collection("whitelist")
    disabled = {
        item["key"]
        for item in store.list_collection("categories")
        if item.get("enabled") is False
    }
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for entity in entities:
        category = entity.get("category") or ""
        if category in disabled:
            skipped.append({**entity, "skipped_by": "category_disabled"})
            continue
        if role_allows(role, category):
            skipped.append({**entity, "skipped_by": "role"})
            continue
        rule = entity_whitelisted(entity, rules)
        if rule:
            skipped.append({**entity, "skipped_by": "whitelist", "rule_id": rule.get("id")})
            continue
        kept.append(entity)
    return kept, skipped


def risk_from_entities(entities: list[dict[str, Any]]) -> RiskLevel:
    levels: list[RiskLevel] = []
    for entity in entities:
        raw = entity.get("risk") or "medium"
        try:
            levels.append(RiskLevel(raw))
        except ValueError:
            levels.append(RiskLevel.MEDIUM)
    return max_risk(levels)


DEDUPE_WINDOW_S = 300
INCIDENT_STATUSES = ("open", "ack", "resolved", "false_positive")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def record_incident(
    store: WorkspaceStore,
    *,
    employee: dict[str, Any] | None,
    role: dict[str, Any] | None,
    scan: dict[str, Any],
    destination: str,
) -> dict[str, Any] | None:
    if scan.get("action") not in {"block", "redact"}:
        return None
    from .gate import dedupe_key, excerpt_of

    labels = sorted({entity.get("label") for entity in scan.get("entities") or [] if entity.get("label")})
    key = dedupe_key((employee or {}).get("id"), destination, labels or [scan.get("kind") or "pii"], scan.get("text") or scan.get("redacted") or "")
    now = _now()
    now_dt = _parse_ts(now)

    existing = None
    for row in store.list_collection("incidents"):
        if row.get("dedupe_key") != key or row.get("status") not in {"open", "ack"}:
            continue
        seen = _parse_ts(row.get("last_seen_at") or row.get("created_at"))
        if seen and now_dt and (now_dt - seen).total_seconds() <= DEDUPE_WINDOW_S:
            existing = row
            break
    if existing is not None:
        updated = {
            **existing,
            "count": int(existing.get("count") or 1) + 1,
            "last_seen_at": now,
            "request_ids": (existing.get("request_ids") or [])[-9:] + [scan.get("request_id")],
        }
        store.upsert("incidents", updated, "inc")
        return {**updated, "duplicate": True}

    item = {
        "id": _id("inc"),
        "created_at": now,
        "last_seen_at": now,
        "count": 1,
        "request_id": scan.get("request_id"),
        "request_ids": [scan.get("request_id")],
        "dedupe_key": key,
        "kind": scan.get("kind") or "pii",
        "direction": scan.get("direction") or "input",
        "employee_id": (employee or {}).get("id"),
        "employee_name": (employee or {}).get("name") or "Unknown",
        "role_name": (role or {}).get("name") or "—",
        "team": (employee or {}).get("team") or "—",
        "destination": destination,
        "model": scan.get("model"),
        "action": scan.get("action"),
        "risk": scan.get("risk"),
        "categories": [item.get("category") for item in scan.get("categories") or []],
        "labels": labels,
        "entities": [
            {
                "label": entity.get("label"),
                "category": entity.get("category"),
                "risk": entity.get("risk"),
                "detected_by": entity.get("detected_by"),
                "control": entity.get("control"),
                "score": entity.get("score"),
                "signature_name": entity.get("signature_name"),
            }
            for entity in scan.get("entities") or []
        ],
        "controls_fired": scan.get("controls_fired") or [],
        "blocked_reason": scan.get("blocked_reason"),
        "redacted": scan.get("redacted") or "",
        "prompt_excerpt": scan.get("prompt_excerpt") or excerpt_of(scan.get("redacted") or ""),
        "policy_version": scan.get("policy_version"),
        "latency_ms": scan.get("latency_ms"),
        "status": "open",
        "assignee": None,
        "note": "",
        "demo": False,
    }
    store.upsert("incidents", item, "inc")
    return item


def execute_gated_scan(layer, store: WorkspaceStore, body) -> dict[str, Any]:
    from .gate import execute_gated_scan as _run

    return _run(layer, store, body)
