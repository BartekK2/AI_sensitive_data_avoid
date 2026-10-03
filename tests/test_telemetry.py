from pathlib import Path

import pytest

from sensitive_guard.telemetry import Telemetry, percentile
from tests._client import CLEAN_TEXT, INJECTION_TEXT, PESEL_TEXT, make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


def test_percentile():
    assert percentile([], 95) == 0
    assert percentile([10], 50) == 10
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) in {5, 5.5, 6}
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 100], 95) >= 9


def test_ring_buffer_is_bounded():
    tele = Telemetry(size=5)
    for index in range(20):
        tele.record({"action": "allow", "kind": "pii", "latency_ms": index, "ts": "2026-10-03T10:00:00+00:00"})
    assert len(tele.snapshot_events(100)) == 5


def test_metrics_shape_and_latency(client):
    scan(client, PESEL_TEXT)
    scan(client, CLEAN_TEXT)
    scan(client, INJECTION_TEXT)
    metrics = client.get("/v1/admin/metrics").json()
    assert 0 <= metrics["posture"]["score"] <= 100
    assert metrics["today"]["block"] >= 2
    assert metrics["today"]["allow"] >= 1
    assert metrics["totals"]["attacks"] >= 1
    assert len(metrics["hourly"]) == 24
    assert len(metrics["last_15_min"]) == 15
    assert metrics["latency_ms"]["samples"] >= 3
    assert metrics["latency_ms"]["p95"] >= metrics["latency_ms"]["p50"]
    assert metrics["backend_split"].get("heuristic", 0) >= 3
    assert any(row["kind"] == "attack" for row in metrics["per_kind"])
    assert metrics["incidents"]["open"] >= 2
    assert metrics["recent"]


def test_posture_drops_when_critical_control_disabled(client):
    base = client.get("/v1/admin/metrics").json()["posture"]["score"]
    client.patch("/v1/admin/controls/pesel_checksum", json={"enabled": False})
    lowered = client.get("/v1/admin/metrics").json()["posture"]
    assert lowered["score"] < base
    assert any("pesel_checksum" in item["reason"] for item in lowered["deductions"])


def test_tests_endpoint_feeds_health(client):
    posted = client.post("/v1/admin/tests", json={"passed": 12, "failed": 1, "ts": "2026-10-03T12:00:00+00:00"})
    assert posted.status_code == 200
    assert posted.json()["ts"] == "2026-10-03T12:00:00+00:00"
    health = client.get("/health").json()
    assert health["tests_last_run"]["passed"] == 12
    assert health["tests_last_run"]["failed"] == 1
    assert "inputs" in health and health["inputs"]["netgate"] is True
    assert health["signatures_count"] > 0


def test_top_people_and_destinations(client):
    scan(client, PESEL_TEXT, employee_id="emp_anna", destination="chatgpt.com")
    scan(client, PESEL_TEXT, employee_id="emp_piotr", destination="claude.ai")
    metrics = client.get("/v1/admin/metrics").json()
    destinations = {row["destination"] for row in metrics["per_destination"]}
    assert {"chatgpt.com", "claude.ai"} <= destinations
    assert metrics["top_people"]
