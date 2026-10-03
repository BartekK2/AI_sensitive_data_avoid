"""HTTP privacy gateway around the Laya sensitive-data layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .gate import GateContext, control_catalog_with_hits, execute_gated_scan
from .layer import SensitiveDataLayer
from .policy import CONTROL_BY_ID, PRESETS, Policy
from .taxonomy import GateAction
from .workspace import INCIDENT_STATUSES, WorkspaceStore, seed

ROOT = Path(__file__).resolve().parents[1]


class ScanRequest(BaseModel):
    text: str
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    region: str = "PL"
    locale: str = "pl"
    collapse: bool = False
    strict: bool | None = None
    employee_id: str | None = None
    employee_email: str | None = None
    destination: str = "ai_chat"
    model: str | None = None
    record: bool = False
    # "input" = prompt on its way to a model, "output" = model response on its way back.
    direction: str = "input"


class ProtectRequest(ScanRequest):
    pass


class RoleIn(BaseModel):
    id: str | None = None
    name: str
    level: str = "standard"
    allowed_categories: list[str] = Field(default_factory=list)
    can_override: bool = False
    description: str = ""


class EmployeeIn(BaseModel):
    id: str | None = None
    name: str
    email: str
    role_id: str
    team: str = ""


class CategoryIn(BaseModel):
    id: str | None = None
    key: str
    label: str
    risk: str = "medium"
    enabled: bool = True
    builtin: bool = False
    min_confidence: float = 0.35


class WhitelistIn(BaseModel):
    id: str | None = None
    type: str
    value: str
    reason: str = ""
    enabled: bool = True


class IncidentPatch(BaseModel):
    status: str | None = None
    note: str | None = None
    assignee: str | None = None


class IncidentBulk(BaseModel):
    ids: list[str]
    status: str | None = None
    assignee: str | None = None
    note: str | None = None


class PolicyPatch(BaseModel):
    preset: str | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    strict: bool | None = None
    category_actions: dict[str, str] | None = None
    destination_overrides: dict[str, dict[str, str]] | None = None
    allowed_models: list[str] | None = None
    scan_output: bool | None = None
    budgets: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    actor: str = "dashboard"


class ControlPatch(BaseModel):
    enabled: bool | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    actor: str = "dashboard"


class SignatureIn(BaseModel):
    id: str | None = None
    name: str
    type: str = "prompt_injection"
    pattern: str
    severity: str = "high"
    source: str = "dashboard"
    enabled: bool = True


class SignatureImport(BaseModel):
    signatures: list[dict[str, Any]]
    source: str = "import"
    replace: bool = False


class TestRunIn(BaseModel):
    passed: int
    failed: int
    skipped: int = 0
    duration_s: float = 0.0
    ts: str | None = None
    finished_at: str | None = None


def _filter_incidents(rows: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    needle = (params.get("q") or "").lower()
    for row in rows:
        if params.get("status") and row.get("status") != params["status"]:
            continue
        if params.get("risk") and row.get("risk") != params["risk"]:
            continue
        if params.get("action") and row.get("action") != params["action"]:
            continue
        if params.get("kind") and (row.get("kind") or "pii") != params["kind"]:
            continue
        if params.get("team") and row.get("team") != params["team"]:
            continue
        if params.get("employee") and params["employee"] not in {row.get("employee_id"), row.get("employee_name")}:
            continue
        if params.get("destination") and params["destination"].lower() not in (row.get("destination") or "").lower():
            continue
        if params.get("category") and params["category"] not in (row.get("categories") or []):
            continue
        if params.get("since") and (row.get("created_at") or "") < params["since"]:
            continue
        if params.get("until") and (row.get("created_at") or "") > params["until"]:
            continue
        if params.get("assignee") and row.get("assignee") != params["assignee"]:
            continue
        if needle:
            blob = " ".join([
                row.get("employee_name") or "",
                row.get("destination") or "",
                row.get("redacted") or "",
                row.get("prompt_excerpt") or "",
                " ".join(row.get("labels") or []),
                " ".join(row.get("categories") or []),
                row.get("note") or "",
            ]).lower()
            if needle not in blob:
                continue
        out.append(row)
    return out


def create_app(
    backend: str = "auto",
    *,
    use_policy: bool = False,
    device: str | None = None,
    store_path: str | Path | None = None,
) -> Any:
    try:
        from fastapi import FastAPI, HTTPException, Query, Request
        from fastapi.responses import FileResponse, PlainTextResponse, Response
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("pip install 'sensitive-guard[serve]'") from exc

    app = FastAPI(
        title="Helios Guard",
        description="AI control layer: deterministic + semantic guardrails, budgets, audit.",
        version="0.2.0",
    )
    try:
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        CORSMiddleware = None
    if CORSMiddleware is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    store = WorkspaceStore(Path(store_path) if store_path else None)
    ctx = GateContext.for_store(store)

    @lru_cache(maxsize=4)
    def layer_for(strict: bool) -> SensitiveDataLayer:
        return SensitiveDataLayer(
            backend=backend,  # type: ignore[arg-type]
            device=device,
            use_policy=use_policy,
            strict=strict,
        )

    def run_scan(body: Any) -> dict[str, Any]:
        return execute_gated_scan(layer_for(bool(getattr(body, "strict", False))), store, body, ctx)

    extension_dir = ROOT / "extension"
    dashboard_dist = ROOT / "dashboard" / "dist"
    if extension_dir.is_dir():
        app.mount("/ext", StaticFiles(directory=extension_dir), name="ext")

        @app.get("/demo")
        def demo_chat() -> FileResponse:
            return FileResponse(
                extension_dir / "test" / "mock-chat.html",
                media_type="text/html; charset=utf-8",
            )

    def health_payload() -> dict[str, Any]:
        probe = layer_for(False)
        policy = ctx.policy.load()
        try:
            from .laya_backend import laya_available

            laya = bool(laya_available())
        except Exception:  # pragma: no cover - optional dependency
            laya = False
        return {
            "ok": True,
            "backend": probe.backend,
            "mode": probe.backend,
            "laya_installed": laya,
            "laya_loaded": probe.backend == "laya",
            "degraded": probe.backend != "laya",
            "policy": use_policy,
            "policy_version": policy.version,
            "policy_preset": policy.preset,
            "policy_mtime": ctx.policy.mtime(),
            "signatures_mtime": ctx.signatures.mtime(),
            "signatures_count": len(ctx.signatures.list()),
            "inputs": {
                "extension": extension_dir.is_dir(),
                "netgate": True,
                "proxy": bool(getattr(app.state, "proxy_port", None)),
                "proxy_port": getattr(app.state, "proxy_port", None),
                "mitm": bool(getattr(app.state, "mitm", False)),
            },
            "tests_last_run": ctx.telemetry.last_test_run or _read_last_tests(),
            "version": "0.2.0",
        }

    def _read_last_tests() -> dict[str, Any] | None:
        path = ROOT / "data" / "last_pytest.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @app.get("/health")
    def health() -> dict[str, Any]:
        return health_payload()

    # ----------------------------------------------------------------- workspace
    @app.get("/v1/admin/workspace")
    def workspace() -> dict[str, Any]:
        data = store.snapshot()
        incidents = data.get("incidents", [])
        open_inc = [item for item in incidents if item.get("status") == "open"]
        return {
            **data,
            "stats": {
                "employees": len(data.get("employees", [])),
                "roles": len(data.get("roles", [])),
                "whitelist": len(data.get("whitelist", [])),
                "open_incidents": len(open_inc),
                "open_critical": sum(1 for item in open_inc if item.get("risk") == "critical"),
                "incidents": len(incidents),
            },
        }

    @app.get("/v1/admin/employees")
    def list_employees() -> list[dict[str, Any]]:
        return store.list_collection("employees")

    @app.post("/v1/admin/employees")
    def save_employee(body: EmployeeIn) -> dict[str, Any]:
        return store.upsert("employees", body.model_dump(), "emp")

    @app.delete("/v1/admin/employees/{item_id}")
    def delete_employee(item_id: str) -> dict[str, bool]:
        if not store.delete("employees", item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    @app.get("/v1/admin/roles")
    def list_roles() -> list[dict[str, Any]]:
        return store.list_collection("roles")

    @app.post("/v1/admin/roles")
    def save_role(body: RoleIn) -> dict[str, Any]:
        return store.upsert("roles", body.model_dump(), "role")

    @app.delete("/v1/admin/roles/{item_id}")
    def delete_role(item_id: str) -> dict[str, bool]:
        if not store.delete("roles", item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    @app.get("/v1/admin/categories")
    def list_categories() -> list[dict[str, Any]]:
        return store.list_collection("categories")

    @app.post("/v1/admin/categories")
    def save_category(body: CategoryIn) -> dict[str, Any]:
        return store.upsert("categories", body.model_dump(), "cat")

    @app.delete("/v1/admin/categories/{item_id}")
    def delete_category(item_id: str) -> dict[str, bool]:
        if not store.delete("categories", item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    @app.get("/v1/admin/whitelist")
    def list_whitelist() -> list[dict[str, Any]]:
        return store.list_collection("whitelist")

    @app.post("/v1/admin/whitelist")
    def save_whitelist(body: WhitelistIn) -> dict[str, Any]:
        return store.upsert("whitelist", body.model_dump(), "wl")

    @app.delete("/v1/admin/whitelist/{item_id}")
    def delete_whitelist(item_id: str) -> dict[str, bool]:
        if not store.delete("whitelist", item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    # ----------------------------------------------------------------- incidents
    @app.get("/v1/admin/incidents")
    def list_incidents(
        status: str | None = None,
        risk: str | None = None,
        action: str | None = None,
        kind: str | None = None,
        team: str | None = None,
        employee: str | None = None,
        destination: str | None = None,
        category: str | None = None,
        assignee: str | None = None,
        since: str | None = None,
        until: str | None = None,
        q: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = Query(default=200, ge=1, le=2000),
        offset: int = Query(default=0, ge=0),
        paged: bool = False,
    ) -> Any:
        rows = store.list_collection("incidents")
        filtered = _filter_incidents(
            rows,
            {
                "status": status, "risk": risk, "action": action, "kind": kind, "team": team,
                "employee": employee, "destination": destination, "category": category,
                "assignee": assignee, "since": since, "until": until, "q": q,
            },
        )
        key = sort if sort in {"created_at", "last_seen_at", "risk", "count", "employee_name", "team"} else "created_at"
        from .taxonomy import RISK_ORDER, RiskLevel

        def sort_value(item: dict[str, Any]) -> Any:
            if key == "risk":
                try:
                    return RISK_ORDER[RiskLevel(item.get("risk") or "none")]
                except ValueError:
                    return 0
            if key == "count":
                return int(item.get("count") or 1)
            return item.get(key) or ""

        filtered.sort(key=sort_value, reverse=(order != "asc"))
        page = filtered[offset: offset + limit]
        if paged:
            teams = sorted({row.get("team") or "—" for row in rows})
            destinations = sorted({row.get("destination") or "—" for row in rows})
            return {"items": page, "total": len(filtered), "offset": offset, "limit": limit,
                    "facets": {"teams": teams, "destinations": destinations}}
        return page

    @app.get("/v1/admin/incidents/export")
    def export_incidents(format: str = "csv", ids: str | None = None, status: str | None = None) -> Response:
        rows = store.list_collection("incidents")
        if ids:
            wanted = set(ids.split(","))
            rows = [row for row in rows if row.get("id") in wanted]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if format == "jsonl":
            body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
            return PlainTextResponse(body, media_type="application/x-ndjson",
                                     headers={"Content-Disposition": "attachment; filename=incidents.jsonl"})
        import csv
        import io

        buffer = io.StringIO()
        columns = ["id", "created_at", "status", "kind", "action", "risk", "employee_name", "team", "role_name",
                   "destination", "model", "categories", "labels", "controls_fired", "count", "assignee", "note", "prompt_excerpt"]
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for field in ("categories", "labels", "controls_fired"):
                if isinstance(flat.get(field), list):
                    flat[field] = "|".join(str(item) for item in flat[field])
            writer.writerow(flat)
        return PlainTextResponse(buffer.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=incidents.csv"})

    @app.patch("/v1/admin/incidents/{item_id}")
    def patch_incident(item_id: str, body: IncidentPatch) -> dict[str, Any]:
        current = next((row for row in store.list_collection("incidents") if row.get("id") == item_id), None)
        if not current:
            raise HTTPException(status_code=404, detail="not found")
        patch = {key: value for key, value in body.model_dump().items() if value is not None}
        if "status" in patch and patch["status"] not in INCIDENT_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {INCIDENT_STATUSES}")
        if patch.get("status") in {"resolved", "false_positive"}:
            from .workspace import _now

            patch["resolved_at"] = _now()
        updated = store.upsert("incidents", {**current, **patch}, "inc")
        ctx.audit.append({"kind": "incident_update", "action": "update", "incident_id": item_id, "patch": patch})
        return updated

    @app.post("/v1/admin/incidents/bulk")
    def bulk_incidents(body: IncidentBulk) -> dict[str, Any]:
        if body.status and body.status not in INCIDENT_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {INCIDENT_STATUSES}")
        patch = {key: value for key, value in body.model_dump().items() if key != "ids" and value is not None}
        wanted = set(body.ids)
        updated = 0

        def mutate(data: dict[str, Any]) -> None:
            nonlocal updated
            for row in data.get("incidents", []):
                if row.get("id") in wanted:
                    row.update(patch)
                    updated += 1

        store.update(mutate)
        ctx.audit.append({"kind": "incident_bulk", "action": "update", "count": updated, "patch": patch})
        return {"ok": True, "updated": updated}

    @app.delete("/v1/admin/incidents/{item_id}")
    def delete_incident(item_id: str) -> dict[str, bool]:
        if not store.delete("incidents", item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    # -------------------------------------------------------------------- policy
    @app.get("/v1/admin/policy")
    def get_policy() -> dict[str, Any]:
        described = ctx.policy.describe()
        described["history"] = ctx.policy.history(50)
        described["preset_definitions"] = PRESETS
        return described

    @app.put("/v1/admin/policy")
    def put_policy(body: dict[str, Any]) -> dict[str, Any]:
        actor = body.pop("actor", "dashboard")
        try:
            policy = Policy.model_validate({**ctx.policy.load().model_dump(), **body})
        except Exception as error:  # pydantic validation
            raise HTTPException(status_code=422, detail=str(error))
        ctx.policy.save(policy, actor=actor, change="policy replaced")
        return ctx.policy.describe()

    @app.patch("/v1/admin/policy")
    def patch_policy(body: PolicyPatch) -> dict[str, Any]:
        patch = {key: value for key, value in body.model_dump().items() if value is not None and key != "actor"}
        if "preset" in patch:
            ctx.policy.use_preset(patch.pop("preset"), actor=body.actor)
        if "budgets" in patch:
            merged = ctx.policy.load().budgets.model_dump()
            merged.update(patch["budgets"])
            patch["budgets"] = merged
        if "agent" in patch:
            merged = ctx.policy.load().agent.model_dump()
            merged.update(patch["agent"])
            patch["agent"] = merged
        if patch:
            try:
                ctx.policy.update(patch, actor=body.actor)
            except Exception as error:
                raise HTTPException(status_code=422, detail=str(error))
        return ctx.policy.describe()

    @app.get("/v1/admin/policy/presets")
    def list_presets() -> dict[str, Any]:
        return PRESETS

    @app.post("/v1/admin/policy/preset/{name}")
    def use_preset(name: str, actor: str = "dashboard") -> dict[str, Any]:
        if name not in PRESETS:
            raise HTTPException(status_code=404, detail="unknown preset")
        ctx.policy.use_preset(name, actor=actor)
        return ctx.policy.describe()

    @app.get("/v1/admin/policy/history")
    def policy_history(limit: int = 100) -> list[dict[str, Any]]:
        return ctx.policy.history(limit)

    @app.get("/v1/admin/policy/export")
    def export_policy() -> Response:
        return PlainTextResponse(
            ctx.policy.load().model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=policy.json"},
        )

    @app.get("/v1/admin/controls")
    def list_controls() -> list[dict[str, Any]]:
        return control_catalog_with_hits(ctx)

    @app.patch("/v1/admin/controls/{control_id}")
    def patch_control(control_id: str, body: ControlPatch) -> dict[str, Any]:
        if control_id not in CONTROL_BY_ID:
            raise HTTPException(status_code=404, detail="unknown control")
        ctx.policy.set_control(control_id, enabled=body.enabled, threshold=body.threshold, actor=body.actor)
        return next(item for item in control_catalog_with_hits(ctx) if item["id"] == control_id)

    # -------------------------------------------------------------------- budget
    @app.get("/v1/admin/budget")
    def get_budget() -> dict[str, Any]:
        return ctx.budget.summary(ctx.policy.load().budgets)

    @app.post("/v1/admin/budget/reset")
    def reset_budget() -> dict[str, Any]:
        ctx.budget.reset()
        ctx.audit.append({"kind": "budget_reset", "action": "reset"})
        return ctx.budget.summary(ctx.policy.load().budgets)

    # ---------------------------------------------------------------- signatures
    @app.get("/v1/admin/signatures")
    def list_signatures() -> dict[str, Any]:
        data = ctx.signatures.snapshot()
        hits: dict[str, int] = {}
        last: dict[str, str] = {}
        for event in ctx.telemetry.snapshot_events(2000):
            for sig in event.get("signature_ids") or []:
                hits[sig] = hits.get(sig, 0) + 1
                last.setdefault(sig, event.get("ts") or "")
        for row in store.list_collection("incidents"):
            for entity in row.get("entities") or []:
                name = entity.get("signature_name")
                if name:
                    hits[name] = hits.get(name, 0) + 1
                    last.setdefault(name, row.get("created_at") or "")
        rows = []
        for row in data.get("signatures", []):
            count = hits.get(row.get("id"), 0) + hits.get(row.get("name"), 0)
            rows.append({**row, "hits": count, "last_hit": last.get(row.get("id")) or last.get(row.get("name"))})
        return {**data, "signatures": rows, "path": str(ctx.signatures.path), "mtime": ctx.signatures.mtime()}

    @app.post("/v1/admin/signatures")
    def save_signature(body: SignatureIn) -> dict[str, Any]:
        import re

        try:
            re.compile(body.pattern)
        except re.error as error:
            raise HTTPException(status_code=422, detail=f"invalid regex: {error}")
        return ctx.signatures.upsert(body.model_dump())

    @app.patch("/v1/admin/signatures/{item_id}")
    def patch_signature(item_id: str, body: dict[str, Any]) -> dict[str, Any]:
        current = next((row for row in ctx.signatures.list() if row.get("id") == item_id), None)
        if not current:
            raise HTTPException(status_code=404, detail="not found")
        return ctx.signatures.upsert({**current, **body, "id": item_id})

    @app.delete("/v1/admin/signatures/{item_id}")
    def delete_signature(item_id: str) -> dict[str, bool]:
        if not ctx.signatures.delete(item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    @app.post("/v1/admin/signatures/import")
    def import_signatures(body: SignatureImport) -> dict[str, Any]:
        count = ctx.signatures.import_feed(body.signatures, source=body.source, replace=body.replace)
        ctx.audit.append({"kind": "signatures_import", "action": "import", "count": count, "source": body.source})
        return {"ok": True, "imported": count, "total": len(ctx.signatures.list())}

    # ---------------------------------------------------------- audit + metrics
    @app.get("/v1/admin/audit")
    def get_audit(
        since: str | None = None,
        until: str | None = None,
        action: str | None = None,
        kind: str | None = None,
        employee: str | None = None,
        team: str | None = None,
        destination: str | None = None,
        direction: str | None = None,
        q: str | None = None,
        limit: int = Query(default=200, ge=1, le=5000),
        format: str = "json",
        reveal: bool = False,
        actor: str = "dashboard",
    ) -> Any:
        rows = ctx.audit.query(
            since=since, until=until, action=action, kind=kind, employee=employee, team=team,
            destination=destination, direction=direction, q=q, limit=limit, reveal=reveal,
        )
        if reveal:
            ctx.audit.append({"kind": "audit_reveal", "action": "reveal", "actor": actor, "rows": len(rows)})
        if format == "csv":
            return PlainTextResponse(ctx.audit.to_csv(rows), media_type="text/csv",
                                     headers={"Content-Disposition": "attachment; filename=audit.csv"})
        if format == "jsonl":
            return PlainTextResponse(ctx.audit.to_jsonl(rows), media_type="application/x-ndjson",
                                     headers={"Content-Disposition": "attachment; filename=audit.jsonl"})
        return {"items": rows, "count": len(rows), "path": str(ctx.audit.path)}

    @app.get("/v1/admin/metrics")
    def get_metrics() -> dict[str, Any]:
        policy = ctx.policy.load()
        described = ctx.policy.describe()
        summary = {
            "disabled_critical": described["disabled_critical"],
            "signatures_enabled": policy.control_enabled("signatures") and bool(ctx.signatures.list()),
        }
        budget = ctx.budget.summary(policy.budgets)
        metrics = ctx.telemetry.metrics(
            incidents=store.list_collection("incidents"),
            policy_summary=summary,
            budget_summary=budget,
            health=health_payload(),
        )
        metrics["budget"] = {
            "exceeded": budget["exceeded"],
            "warnings": budget["warnings"],
            "totals": budget["totals"],
            "split": budget["split"],
        }
        metrics["recent"] = ctx.telemetry.snapshot_events(30)
        return metrics

    @app.post("/v1/admin/tests")
    def post_tests(body: TestRunIn) -> dict[str, Any]:
        payload = body.model_dump()
        payload["ts"] = payload.get("ts") or payload.get("finished_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        ctx.telemetry.last_test_run = payload
        return payload

    # ---------------------------------------------------------------------- demo
    @app.post("/v1/admin/demo/reset")
    def demo_reset(keep_live: bool = True) -> dict[str, Any]:
        fresh = seed()

        def mutate(data: dict[str, Any]) -> None:
            live = [row for row in data.get("incidents", []) if not row.get("demo")] if keep_live else []
            data["incidents"] = live
            data["usage"] = {"employees": {}, "teams": {}, "models": {}}
            for key in ("roles", "employees", "categories", "whitelist"):
                if key not in data or not data[key]:
                    data[key] = fresh[key]

        store.update(mutate)
        ctx.audit.append({"kind": "demo_reset", "action": "reset", "keep_live": keep_live})
        return {"ok": True, "incidents": len(store.list_collection("incidents"))}

    @app.post("/v1/admin/demo/clear-live")
    def demo_clear_live() -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> None:
            data["incidents"] = [row for row in data.get("incidents", []) if row.get("demo")]

        store.update(mutate)
        return {"ok": True, "incidents": len(store.list_collection("incidents"))}

    # ---------------------------------------------------------------------- scan
    @app.post("/v1/scan")
    def scan(body: ScanRequest) -> dict[str, Any]:
        return run_scan(body)

    @app.post("/v1/protect")
    def protect(body: ProtectRequest) -> dict[str, Any]:
        payload = run_scan(body)
        if payload.get("action") == GateAction.BLOCK.value:
            raise HTTPException(status_code=409, detail=payload)
        return payload

    if dashboard_dist.is_dir():
        app.mount("/app", StaticFiles(directory=dashboard_dist, html=True), name="dashboard")

    from .netgate import register_net_routes

    register_net_routes(app, run_scan=run_scan, ctx=ctx)
    app.state.gate_ctx = ctx
    app.state.store = store
    return app
