"""HTTP privacy gateway around the Laya sensitive-data layer."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .layer import SensitiveDataLayer
from .taxonomy import GateAction
from .workspace import WorkspaceStore, execute_gated_scan


class ScanRequest(BaseModel):
    text: str
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    region: str = "PL"
    locale: str = "pl"
    collapse: bool = False
    strict: bool | None = None
    employee_id: str | None = None
    employee_email: str | None = None
    destination: str = "ai_chat"
    record: bool = False


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


class WhitelistIn(BaseModel):
    id: str | None = None
    type: str
    value: str
    reason: str = ""
    enabled: bool = True


class IncidentPatch(BaseModel):
    status: str | None = None
    note: str | None = None


def create_app(
    backend: str = "auto",
    *,
    use_policy: bool = False,
    device: str | None = None,
    store_path: str | Path | None = None,
) -> Any:
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("pip install 'sensitive-guard[serve]'") from exc

    app = FastAPI(
        title="sensitive-guard",
        description="Laya-powered layer that detects and categorizes sensitive data.",
        version="0.1.0",
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

    @lru_cache(maxsize=4)
    def layer_for(strict: bool) -> SensitiveDataLayer:
        return SensitiveDataLayer(
            backend=backend,  # type: ignore[arg-type]
            device=device,
            use_policy=use_policy,
            strict=strict,
        )

    def run_scan(body: ScanRequest) -> dict[str, Any]:
        return execute_gated_scan(layer_for(bool(body.strict)), store, body)

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    extension_dir = Path(__file__).resolve().parents[1] / "extension"
    dashboard_dist = Path(__file__).resolve().parents[1] / "dashboard" / "dist"
    if extension_dir.is_dir():
        app.mount("/ext", StaticFiles(directory=extension_dir), name="ext")

        @app.get("/demo")
        def demo_chat() -> FileResponse:
            return FileResponse(
                extension_dir / "test" / "mock-chat.html",
                media_type="text/html; charset=utf-8",
            )

    @app.get("/health")
    def health() -> dict[str, Any]:
        probe = layer_for(False)
        return {"ok": True, "backend": probe.backend, "policy": use_policy}

    @app.get("/v1/admin/workspace")
    def workspace() -> dict[str, Any]:
        data = store.snapshot()
        open_inc = sum(1 for item in data.get("incidents", []) if item.get("status") == "open")
        return {
            **data,
            "stats": {
                "employees": len(data.get("employees", [])),
                "roles": len(data.get("roles", [])),
                "whitelist": len(data.get("whitelist", [])),
                "open_incidents": open_inc,
                "incidents": len(data.get("incidents", [])),
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

    @app.get("/v1/admin/incidents")
    def list_incidents() -> list[dict[str, Any]]:
        rows = store.list_collection("incidents")
        return sorted(rows, key=lambda item: item.get("created_at") or "", reverse=True)

    @app.patch("/v1/admin/incidents/{item_id}")
    def patch_incident(item_id: str, body: IncidentPatch) -> dict[str, Any]:
        current = next((row for row in store.list_collection("incidents") if row.get("id") == item_id), None)
        if not current:
            raise HTTPException(status_code=404, detail="not found")
        patch = {key: value for key, value in body.model_dump().items() if value is not None}
        return store.upsert("incidents", {**current, **patch}, "inc")

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

    register_net_routes(app, run_scan=run_scan)
    return app
