import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from sensitive_guard.layer import SensitiveDataLayer
from sensitive_guard.netgate import inspect_and_maybe_redact, map_upstream
from sensitive_guard.serve import create_app
from sensitive_guard.workspace import WorkspaceStore, execute_gated_scan, seed


@pytest.fixture
def client(tmp_path: Path):
    path = tmp_path / "ws.json"
    path.write_text(json.dumps(seed()), encoding="utf-8")
    return TestClient(create_app(backend="heuristic", store_path=path))


def test_map_upstream():
    vendor, url = map_upstream("/openai/v1/chat/completions")
    assert vendor == "openai"
    assert url.endswith("/v1/chat/completions")
    assert map_upstream("/nope/x") is None


def test_blocks_pesel_in_openai_body(client):
    response = client.post(
        "/net/openai/v1/chat/completions",
        headers={"x-employee-id": "emp_anna", "content-type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "mój pesel: 0828282, napisz CV"}],
        },
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "sensitive_data_blocked"
    assert body["scan"]["action"] == "block"


def test_inspect_allows_clean_json(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "ws.json")
    store._write(seed())
    layer = SensitiveDataLayer(backend="heuristic")
    gated = inspect_and_maybe_redact(
        json.dumps({"messages": [{"role": "user", "content": "Wytlumacz sieci neuronowe."}]}).encode(),
        "application/json",
        lambda body: execute_gated_scan(layer, store, body),
        "emp_anna",
        "openai",
    )
    assert gated["action"] == "allow"


def test_net_health(client):
    health = client.get("/net/health")
    assert health.status_code == 200
    assert "openai" in health.json()["upstreams"]
    assert "OPENAI_BASE_URL" in health.json()["env"]
