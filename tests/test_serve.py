from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from sensitive_guard.serve import create_app
from sensitive_guard.workspace import seed


@pytest.fixture
def client(tmp_path: Path):
    path = tmp_path / "ws.json"
    path.write_text(__import__("json").dumps(seed()), encoding="utf-8")
    return TestClient(create_app(backend="heuristic", store_path=path))


def test_health_and_scan(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    scan = client.post(
        "/v1/scan",
        json={"text": "mail billing@acme.example PESEL 44051401359", "locale": "pl"},
    )
    assert scan.status_code == 200
    body = scan.json()
    assert body["action"] == "block"
    assert any(entity["label"] == "pesel" for entity in body["entities"])


def test_demo_page(client):
    page = client.get("/demo")
    assert page.status_code == 200
    assert "prompt-textarea" in page.text
    assets = client.get("/ext/lib.js")
    assert assets.status_code == 200
    assert "SensitiveGuardLib" in assets.text


def test_admin_and_incident(client):
    workspace = client.get("/v1/admin/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["stats"]["employees"] >= 1

    scan = client.post(
        "/v1/scan",
        json={
            "text": "PESEL 44051401359",
            "locale": "pl",
            "employee_id": "emp_anna",
            "destination": "chatgpt.com",
            "record": True,
        },
    )
    assert scan.status_code == 200
    assert scan.json()["action"] == "block"
    assert scan.json()["incident"]["employee_name"] == "Anna Nowak"

    incidents = client.get("/v1/admin/incidents").json()
    assert any(item["id"] == scan.json()["incident"]["id"] for item in incidents)

    allowed = client.post(
        "/v1/scan",
        json={"text": "napisz do pomoc@helios.pl", "employee_id": "emp_anna"},
    )
    assert allowed.json()["action"] == "allow"
    assert allowed.json()["incident"] is None
