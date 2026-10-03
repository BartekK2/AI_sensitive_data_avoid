from pathlib import Path

import pytest

from sensitive_guard.budget import estimate_tokens
from tests._client import CLEAN_TEXT, make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_budget_blocks_after_limit_and_resets(client):
    client.patch("/v1/admin/policy", json={"budgets": {"limits": {"employees": {"emp_anna": 60}, "teams": {}, "models": {}}}})
    long_text = "word " * 40  # 50 tokens: first request fits, the second would reach 100 > 60

    first = scan(client, long_text)
    assert first["action"] == "allow"
    assert first["budget"]["pct"] >= 0

    second = scan(client, long_text)
    assert second["action"] == "block"
    assert second["kind"] == "budget"
    assert "budget" in second["controls_fired"]
    assert second["incident"] is not None

    summary = client.get("/v1/admin/budget").json()
    assert "employee:emp_anna" in summary["exceeded"]
    anna = next(row for row in summary["employees"] if row["key"] == "emp_anna")
    assert anna["pct"] >= 80  # consumed tokens stay below the limit; the block itself marks it exceeded
    assert anna["blocked"] >= 1
    assert anna["budget_blocks"] == 1

    client.post("/v1/admin/budget/reset")
    assert scan(client, long_text)["action"] == "allow"


def test_budget_warning_at_alert_pct(client):
    client.patch("/v1/admin/policy", json={"budgets": {"alert_pct": 50, "limits": {"employees": {"emp_anna": 100}, "teams": {}, "models": {}}}})
    scan(client, "x" * 240)  # 60 tokens → 60 %
    result = scan(client, "ok")
    assert result["action"] == "allow"
    assert result["budget"]["warnings"]
    summary = client.get("/v1/admin/budget").json()
    assert any(item["key"] == "emp_anna" for item in summary["warnings"])


def test_budget_disabled_never_blocks(client):
    client.patch("/v1/admin/policy", json={"budgets": {"enabled": False, "limits": {"employees": {"emp_anna": 1}, "teams": {}, "models": {}}}})
    for _ in range(3):
        assert scan(client, CLEAN_TEXT)["action"] == "allow"


def test_rate_limit_returns_block_kind(client):
    client.patch("/v1/admin/policy", json={"budgets": {"requests_per_min": 2}})
    assert scan(client, CLEAN_TEXT)["action"] == "allow"
    assert scan(client, CLEAN_TEXT)["action"] == "allow"
    third = scan(client, CLEAN_TEXT)
    assert third["action"] == "block"
    assert third["kind"] == "rate_limit"

    # Disabling the control switches the limiter off without changing the number.
    client.patch("/v1/admin/controls/rate_limit", json={"enabled": False})
    assert scan(client, CLEAN_TEXT)["action"] == "allow"


def test_netgate_budget_is_429(client):
    client.patch("/v1/admin/policy", json={"budgets": {"requests_per_min": 1}})
    headers = {"x-employee-id": "emp_anna"}
    body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": CLEAN_TEXT}]}
    client.post("/net/openai/v1/chat/completions", headers=headers, json=body)  # consumes the slot (may 502 upstream)
    response = client.post("/net/openai/v1/chat/completions", headers=headers, json=body)
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"


def test_cost_and_local_split(client):
    client.patch("/v1/admin/policy", json={"budgets": {"cost_per_1k": {"gpt-4o-mini": 1.0}, "local_models": ["llama"]}})
    scan(client, "a" * 4000, model="gpt-4o-mini")  # 1000 tokens → $1.00
    scan(client, "a" * 400, model="llama3")
    summary = client.get("/v1/admin/budget").json()
    gpt = next(row for row in summary["models"] if row["key"] == "gpt-4o-mini")
    assert gpt["cost"] == pytest.approx(1.0, abs=0.01)
    assert summary["split"]["local"] == 100
    assert summary["split"]["cloud"] >= 1000
