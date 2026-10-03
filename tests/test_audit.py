from pathlib import Path

import pytest

from sensitive_guard.audit import EXPORT_COLUMNS, AuditLog, mask_value
from tests._client import CLEAN_TEXT, PESEL_TEXT, make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


def test_mask_value_keeps_shape():
    assert mask_value("") == ""
    assert mask_value("abc") == "***"
    masked = mask_value("44051401359")
    assert masked.startswith("44") and masked.endswith("59") and "0514" not in masked


def test_audit_log_append_query_and_redaction(tmp_path: Path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append({"action": "block", "employee_id": "e1", "raw_values": ["secret"], "masked_values": ["se**et"]})
    log.append({"action": "allow", "employee_id": "e2"})
    assert len(log.tail(10)) == 2
    blocked = log.query(action="block")
    assert len(blocked) == 1
    assert "raw_values" not in blocked[0]
    revealed = log.query(action="block", reveal=True)
    assert revealed[0]["raw_values"] == ["secret"]
    csv_text = log.to_csv(blocked)
    assert csv_text.splitlines()[0] == ",".join(EXPORT_COLUMNS)
    assert "secret" not in csv_text


def test_every_decision_lands_in_audit(client):
    scan(client, PESEL_TEXT)
    scan(client, CLEAN_TEXT)
    rows = client.get("/v1/admin/audit").json()["items"]
    actions = {row["action"] for row in rows if row.get("kind") in {"pii", "attack"}}
    assert {"block", "allow"} <= actions
    blocked = next(row for row in rows if row["action"] == "block")
    assert blocked["employee_name"] == "Anna Nowak"
    assert blocked["masked_values"]
    assert "raw_values" not in blocked
    assert "44051401359" not in str(blocked)


def test_reveal_is_itself_audited(client):
    scan(client, PESEL_TEXT)
    revealed = client.get("/v1/admin/audit", params={"reveal": "true", "action": "block"}).json()["items"]
    assert any("44051401359" in (row.get("raw_values") or []) for row in revealed)
    after = client.get("/v1/admin/audit", params={"kind": "audit_reveal"}).json()["items"]
    assert after and after[0]["action"] == "reveal"


def test_audit_filters_and_exports(client):
    scan(client, PESEL_TEXT, destination="claude.ai")
    scan(client, PESEL_TEXT, destination="chatgpt.com", employee_id="emp_piotr")
    by_dest = client.get("/v1/admin/audit", params={"destination": "claude.ai"}).json()["items"]
    assert by_dest and all(row["destination"] == "claude.ai" for row in by_dest)
    by_emp = client.get("/v1/admin/audit", params={"employee": "emp_piotr"}).json()["items"]
    assert by_emp and all(row["employee_id"] == "emp_piotr" for row in by_emp)
    by_q = client.get("/v1/admin/audit", params={"q": "pesel"}).json()["items"]
    assert by_q

    csv_response = client.get("/v1/admin/audit", params={"format": "csv"})
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert csv_response.text.startswith("ts,request_id")
    jsonl = client.get("/v1/admin/audit", params={"format": "jsonl"})
    assert jsonl.text.strip().splitlines()


def test_policy_changes_are_audited(client):
    client.post("/v1/admin/policy/preset/strict")
    client.patch("/v1/admin/controls/pesel_checksum", json={"enabled": False})
    history = client.get("/v1/admin/policy/history").json()
    assert any("preset strict" in row["change"] for row in history)
    assert any("pesel_checksum" in row["change"] for row in history)
