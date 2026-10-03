from pathlib import Path

import pytest

from sensitive_guard.policy import Policy
from tests._client import CLEAN_TEXT, make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


def test_model_allowed_matching():
    policy = Policy(allowed_models=["gpt-4o-mini", "claude-3*"])
    assert policy.model_allowed("gpt-4o-mini")
    assert policy.model_allowed("claude-3-5-sonnet")
    assert not policy.model_allowed("gpt-4o")
    assert not policy.model_allowed("shadow-llm")
    assert Policy(allowed_models=[]).model_allowed("anything")


def test_scan_blocks_unknown_model(client):
    client.patch("/v1/admin/policy", json={"allowed_models": ["gpt-4o-mini"]})
    result = scan(client, CLEAN_TEXT, model="shadow-llm-9000")
    assert result["action"] == "block"
    assert result["kind"] == "model"
    assert result["controls_fired"] == ["model_allowlist"]
    assert result["incident"]["kind"] == "model"
    assert scan(client, CLEAN_TEXT, model="gpt-4o-mini")["action"] == "allow"


def test_empty_allowlist_allows_everything(client):
    client.patch("/v1/admin/policy", json={"allowed_models": []})
    assert scan(client, CLEAN_TEXT, model="whatever-7b")["action"] == "allow"


def test_netgate_model_not_allowed_is_403(client):
    client.patch("/v1/admin/policy", json={"allowed_models": ["gpt-4o-mini"]})
    response = client.post(
        "/net/openai/v1/chat/completions",
        headers={"x-employee-id": "emp_anna"},
        json={"model": "shadow-llm-9000", "messages": [{"role": "user", "content": CLEAN_TEXT}]},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "model_not_allowed"
    assert body["kind"] == "model"
    assert response.headers["X-Helios-Policy-Version"]


def test_netgate_tool_allowlist(client):
    client.patch("/v1/admin/policy", json={"agent": {"allowed_tools": ["search_docs"]}})
    response = client.post(
        "/net/openai/v1/chat/completions",
        headers={"x-employee-id": "emp_anna"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Delete the production database."}],
            "tools": [{"type": "function", "function": {"name": "shell_exec", "parameters": {}}}],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"] == "tool_not_allowed"
    assert "tool_allowlist" in response.json()["scan"]["controls_fired"]


def test_netgate_memory_isolation(client):
    foreign = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": "memory: employee_id=emp_piotr ..."}, {"role": "user", "content": CLEAN_TEXT}]}
    response = client.post("/net/openai/v1/chat/completions", headers={"x-employee-id": "emp_anna"}, json=foreign)
    assert response.status_code == 403
    assert response.json()["error"] == "memory_isolation"
    assert response.json()["scan"]["risk"] == "critical"

    # Own context is fine.
    own = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": "memory: employee_id=emp_anna"}, {"role": "user", "content": CLEAN_TEXT}]}
    assert client.post("/net/openai/v1/chat/completions", headers={"x-employee-id": "emp_anna"}, json=own).status_code != 403

    client.patch("/v1/admin/controls/memory_isolation", json={"enabled": False})
    response = client.post("/net/openai/v1/chat/completions", headers={"x-employee-id": "emp_anna"}, json=foreign)
    assert response.status_code != 403


def test_loop_guard(client):
    client.patch("/v1/admin/policy", json={"agent": {"loop_max_repeats": 2, "loop_window_s": 60}})
    assert scan(client, "same prompt")["action"] == "allow"
    assert scan(client, "same prompt")["action"] == "allow"
    third = scan(client, "same prompt")
    assert third["action"] == "block"
    assert third["kind"] == "loop"
    assert scan(client, "different prompt")["action"] == "allow"
