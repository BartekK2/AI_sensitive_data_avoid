import json
from pathlib import Path

import pytest

from sensitive_guard.layer import SensitiveDataLayer
from sensitive_guard.netgate import response_text, scan_response
from sensitive_guard.workspace import WorkspaceStore, execute_gated_scan, seed
from tests._client import make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


@pytest.fixture
def runner(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "ws.json")
    store._write(seed())
    layer = SensitiveDataLayer(backend="heuristic")
    return store, (lambda body: execute_gated_scan(layer, store, body))


def test_response_text_extracts_vendor_shapes():
    openai = {"choices": [{"message": {"content": "hello"}}]}
    anthropic = {"content": [{"type": "text", "text": "world"}]}
    assert response_text(openai) == "hello"
    assert response_text(anthropic) == "world"
    assert response_text({"nothing": True}) == ""


def test_output_with_pesel_is_redacted(runner):
    store, run = runner
    raw = json.dumps({"choices": [{"message": {"role": "assistant", "content": "Klient: PESEL 44051401359, dalej..."}}]}).encode()
    rewritten, scan_result = scan_response(raw, "application/json", run, "emp_anna", "openai", "gpt-4o-mini")
    assert scan_result is not None
    assert scan_result["direction"] == "output"
    assert "44051401359" not in rewritten.decode()
    assert "[PESEL]" in rewritten.decode()
    incidents = store.list_collection("incidents")
    assert any(row.get("direction") == "output" for row in incidents)


def test_clean_output_untouched(runner):
    _, run = runner
    raw = json.dumps({"choices": [{"message": {"content": "The roadmap has three themes."}}]}).encode()
    rewritten, scan_result = scan_response(raw, "application/json", run, "emp_anna", "openai", "gpt-4o-mini")
    assert rewritten == raw
    assert scan_result["action"] == "allow"


def test_non_json_output_passthrough(runner):
    _, run = runner
    raw = b"data: {\"choices\": []}\n\n"
    rewritten, scan_result = scan_response(raw, "text/event-stream", run, "emp_anna", "openai", None)
    assert rewritten == raw
    assert scan_result is None


def test_output_direction_is_recorded_in_audit(client):
    result = scan(client, "Odpowiedź modelu: PESEL 44051401359", direction="output")
    assert result["direction"] == "output"
    rows = client.get("/v1/admin/audit", params={"direction": "output"}).json()["items"]
    assert rows
    assert rows[0]["direction"] == "output"
    # Output never consumes the budget or hits the rate limiter.
    summary = client.get("/v1/admin/budget").json()
    anna = next((row for row in summary["employees"] if row["key"] == "emp_anna"), None)
    assert anna is None or anna["tokens"] == 0


def test_scan_output_flag_in_policy(client):
    policy = client.patch("/v1/admin/policy", json={"scan_output": False}).json()["policy"]
    assert policy["scan_output"] is False
    policy = client.patch("/v1/admin/policy", json={"scan_output": True}).json()["policy"]
    assert policy["scan_output"] is True
