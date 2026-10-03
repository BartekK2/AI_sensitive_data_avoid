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
    item = {
        "id": _id("inc"),
        "created_at": _now(),
        "employee_id": (employee or {}).get("id"),
        "employee_name": (employee or {}).get("name") or "Nieznany",
        "role_name": (role or {}).get("name") or "—",
        "team": (employee or {}).get("team") or "—",
        "destination": destination,
        "action": scan.get("action"),
        "risk": scan.get("risk"),
        "categories": [item.get("category") for item in scan.get("categories") or []],
        "labels": sorted({entity.get("label") for entity in scan.get("entities") or [] if entity.get("label")}),
        "redacted": scan.get("redacted") or "",
        "status": "open",
        "note": "",
    }
    store.upsert("incidents", item, "inc")
    return item


def execute_gated_scan(layer, store: WorkspaceStore, body) -> dict[str, Any]:
    from .taxonomy import action_for_risk

    result = layer.scan(
        body.text,
        threshold=getattr(body, "threshold", 0.5),
        region=getattr(body, "region", "PL"),
        locale=getattr(body, "locale", "pl"),
        collapse=getattr(body, "collapse", False),
    )
    payload = result.model_dump()
    employee = store.employee_by_id_or_email(getattr(body, "employee_id", None), getattr(body, "employee_email", None))
    actor_name = getattr(body, "actor_name", None)
    actor_team = getattr(body, "actor_team", None)
    if employee is None and actor_name:
        employee = {"id": None, "name": actor_name, "team": actor_team or "—", "role_id": None}
    role = store.role_for(employee)
    if role is None and actor_name and employee and not employee.get("role_id"):
        role = {"name": "Antigravity"}
    kept, skipped = apply_workspace_policy(payload.get("entities") or [], store=store, employee=employee)
    payload["entities"] = kept
    payload["skipped"] = skipped
    payload["policy_applied"] = True
    if kept:
        from .models import Entity, summarize_categories

        rebuilt = [Entity.model_validate(item) for item in kept]
        payload["categories"] = [item.model_dump() for item in summarize_categories(rebuilt)]
        risk = risk_from_entities(kept)
        payload["risk"] = risk.value
        payload["action"] = action_for_risk(risk, strict=bool(getattr(body, "strict", False))).value
    else:
        payload["categories"] = []
        payload["risk"] = "none"
        payload["action"] = "allow"
    payload["employee"] = employee
    payload["role"] = role
    payload["incident"] = None
    if getattr(body, "record", False):
        payload["incident"] = record_incident(
            store,
            employee=employee,
            role=role,
            scan=payload,
            destination=getattr(body, "destination", "ai_chat"),
        )
    return payload
