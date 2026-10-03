from pathlib import Path

import pytest

from sensitive_guard.workspace import INCIDENT_STATUSES
from tests._client import INJECTION_TEXT, PESEL_TEXT, make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


def test_repeat_is_deduplicated_into_count(client):
    first = scan(client, PESEL_TEXT)["incident"]
    second = scan(client, PESEL_TEXT)["incident"]
    assert second["id"] == first["id"]
    assert second.get("duplicate") is True
    assert second["count"] == 2
    listed = client.get("/v1/admin/incidents", params={"paged": "true", "q": "pesel"}).json()
    row = next(item for item in listed["items"] if item["id"] == first["id"])
    assert row["count"] == 2
    assert row["last_seen_at"] >= row["created_at"]


def test_incident_payload_has_evidence(client):
    incident = scan(client, PESEL_TEXT)["incident"]
    assert incident["kind"] == "pii"
    assert incident["status"] == "open"
    assert incident["controls_fired"]
    assert incident["entities"][0]["detected_by"] in {"regex", "checksum", "heuristic", "classifier", "signature"}
    assert "44051401359" not in incident["redacted"]
    assert "44051401359" not in incident["prompt_excerpt"]
    assert incident["policy_version"] >= 1
    assert incident["latency_ms"] >= 0


def test_patch_status_note_assignee(client):
    incident = scan(client, PESEL_TEXT)["incident"]
    patched = client.patch(f"/v1/admin/incidents/{incident['id']}", json={"status": "ack", "note": "talked to Anna", "assignee": "emp_tomasz"})
    assert patched.status_code == 200
    body = patched.json()
    assert body["status"] == "ack" and body["note"] == "talked to Anna" and body["assignee"] == "emp_tomasz"
    assert client.patch(f"/v1/admin/incidents/{incident['id']}", json={"status": "bogus"}).status_code == 422
    assert client.patch("/v1/admin/incidents/nope", json={"status": "ack"}).status_code == 404
    assert set(INCIDENT_STATUSES) == {"open", "ack", "resolved", "false_positive"}


def test_bulk_and_filters(client):
    a = scan(client, PESEL_TEXT)["incident"]["id"]
    b = scan(client, INJECTION_TEXT)["incident"]["id"]
    result = client.post("/v1/admin/incidents/bulk", json={"ids": [a, b], "status": "resolved"}).json()
    assert result["updated"] == 2
    resolved = client.get("/v1/admin/incidents", params={"status": "resolved"}).json()
    assert {a, b} <= {row["id"] for row in resolved}

    attacks = client.get("/v1/admin/incidents", params={"kind": "attack"}).json()
    assert attacks and all(row["kind"] == "attack" for row in attacks)

    paged = client.get("/v1/admin/incidents", params={"paged": "true", "limit": 1, "sort": "risk"}).json()
    assert paged["total"] >= 2 and len(paged["items"]) == 1
    assert "teams" in paged["facets"] and "destinations" in paged["facets"]
    assert client.post("/v1/admin/incidents/bulk", json={"ids": [a], "status": "weird"}).status_code == 422


def test_export_masks_and_deletes(client):
    incident_id = scan(client, PESEL_TEXT)["incident"]["id"]
    csv_text = client.get("/v1/admin/incidents/export", params={"format": "csv", "ids": incident_id}).text
    assert csv_text.startswith("id,created_at,status")
    assert "44051401359" not in csv_text
    jsonl = client.get("/v1/admin/incidents/export", params={"format": "jsonl", "ids": incident_id}).text
    assert "44051401359" not in jsonl
    assert client.delete(f"/v1/admin/incidents/{incident_id}").status_code == 200
    assert client.delete(f"/v1/admin/incidents/{incident_id}").status_code == 404


def test_role_exception_prevents_incident(client):
    workspace = client.get("/v1/admin/workspace").json()
    hr_role = next(role for role in workspace["roles"] if "contact" in (role.get("allowed_categories") or []))
    hr_person = next(person for person in workspace["employees"] if person["role_id"] == hr_role["id"])
    phone = "Zadzwoń pod +48 600 100 200 do kandydata."
    result = scan(client, phone, employee_id=hr_person["id"])
    assert result["action"] == "allow"
    assert result["incident"] is None
    assert "roles" in result["controls_fired"]


def test_demo_reset_keeps_live(client):
    live = scan(client, PESEL_TEXT)["incident"]["id"]
    client.post("/v1/admin/demo/reset", params={"keep_live": "true"})
    ids = {row["id"] for row in client.get("/v1/admin/incidents").json()}
    assert live in ids
    assert not any(row.get("demo") for row in client.get("/v1/admin/incidents").json())
    client.post("/v1/admin/demo/clear-live")
    assert live not in {row["id"] for row in client.get("/v1/admin/incidents").json()}
