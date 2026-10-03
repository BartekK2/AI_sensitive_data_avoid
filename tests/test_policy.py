import json
import os
import time
from pathlib import Path

import pytest

from tests._client import CLEAN_TEXT, PESEL_TEXT, make_client, scan


@pytest.fixture
def client(tmp_path: Path):
    return make_client(tmp_path)


def test_policy_describe_and_version_in_scan(client):
    policy = client.get("/v1/admin/policy").json()
    assert policy["policy"]["preset"] in {"strict", "balanced", "permissive"}
    assert any(item["id"] == "pesel_checksum" for item in policy["controls"])

    result = scan(client, PESEL_TEXT)
    assert result["policy_version"] == policy["policy"]["version"]
    assert result["request_id"].startswith("req_")
    assert result["latency_ms"] >= 0
    assert "pesel_checksum" in result["controls_fired"]


def test_presets_change_threshold_and_history(client):
    before = client.get("/v1/admin/policy").json()["policy"]["version"]
    strict = client.post("/v1/admin/policy/preset/strict").json()["policy"]
    assert strict["preset"] == "strict"
    assert strict["strict"] is True
    assert strict["version"] == before + 1

    permissive = client.post("/v1/admin/policy/preset/permissive").json()["policy"]
    assert permissive["threshold"] > strict["threshold"]

    history = client.get("/v1/admin/policy/history").json()
    assert any("preset strict" in row["change"] for row in history)
    assert client.post("/v1/admin/policy/preset/nope").status_code == 404


def test_disabling_pesel_checksum_lets_pesel_through(client):
    assert scan(client, PESEL_TEXT)["action"] == "block"

    patched = client.patch("/v1/admin/controls/pesel_checksum", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    result = scan(client, "PESEL 44051401359")
    assert all(entity["label"] != "pesel" for entity in result["entities"])
    assert "pesel_checksum" in result.get("disabled_controls", []) or result["action"] != "block"

    client.patch("/v1/admin/controls/pesel_checksum", json={"enabled": True})
    assert scan(client, PESEL_TEXT)["action"] == "block"
    assert client.patch("/v1/admin/controls/does_not_exist", json={"enabled": False}).status_code == 404


PHONE = "Zadzwoń pod +48 600 100 200 do działu sprzedaży."


def test_category_action_override(client):
    # Phone numbers are "contact" → redact by default (medium risk); force block, then allow.
    # "gemini.google.com" has no seed destination override, so the category action decides.
    dest = "gemini.google.com"
    assert scan(client, PHONE, destination=dest)["action"] == "redact"
    client.patch("/v1/admin/policy", json={"category_actions": {"contact": "block"}})
    assert scan(client, PHONE, destination=dest)["action"] == "block"
    client.patch("/v1/admin/policy", json={"category_actions": {"contact": "allow"}})
    result = scan(client, PHONE, destination=dest)
    assert result["action"] == "allow"
    assert result["incident"] is None


def test_destination_override_beats_category_action(client):
    client.patch(
        "/v1/admin/policy",
        json={"category_actions": {"contact": "allow"}, "destination_overrides": {"claude.ai": {"contact": "block"}}},
    )
    assert scan(client, PHONE, destination="gemini.google.com")["action"] == "allow"
    assert scan(client, PHONE, destination="claude.ai")["action"] == "block"
    # Seed policy: chatgpt.com forces contact → redact regardless of the category default.
    seeded = client.get("/v1/admin/policy").json()["policy"]["destination_overrides"]
    assert seeded["claude.ai"] == {"contact": "block"}


def test_threshold_patch_validates(client):
    assert client.patch("/v1/admin/policy", json={"threshold": 1.5}).status_code == 422
    ok = client.patch("/v1/admin/policy", json={"threshold": 0.9}).json()["policy"]
    assert ok["threshold"] == 0.9
    assert scan(client, CLEAN_TEXT)["threshold_used"] == 0.9
    assert scan(client, CLEAN_TEXT, threshold=0.2)["threshold_used"] == 0.2


def test_hot_reload_from_disk(client, tmp_path: Path):
    described = client.get("/v1/admin/policy").json()
    path = Path(described["path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["threshold"] = 0.77
    data["version"] = data["version"] + 10
    time.sleep(0.01)
    path.write_text(json.dumps(data), encoding="utf-8")
    # Force a different mtime on filesystems with coarse resolution.
    future = time.time() + 5
    os.utime(path, (future, future))

    reloaded = client.get("/v1/admin/policy").json()["policy"]
    assert reloaded["threshold"] == 0.77
    assert reloaded["version"] == data["version"]
    assert client.get("/health").json()["policy_version"] == data["version"]


def test_put_and_export_policy(client):
    current = client.get("/v1/admin/policy").json()["policy"]
    current["allowed_models"] = ["gpt-4o*"]
    assert client.put("/v1/admin/policy", json=current).status_code == 200
    exported = client.get("/v1/admin/policy/export")
    assert exported.status_code == 200
    assert json.loads(exported.text)["allowed_models"] == ["gpt-4o*"]
    assert client.put("/v1/admin/policy", json={"threshold": "not-a-number"}).status_code == 422


def test_topic_confidence_slider():
    from sensitive_guard.topics import kept_topics

    category = {"key": "wojsko", "label": "wojsko", "enabled": True, "builtin": False, "min_confidence": 0.35, "risk": "medium"}
    assert kept_topics({"wojsko": 0.62}, [category])[0]["confidence"] == 0.62
    assert kept_topics({"wojsko": 0.2}, [category]) == []
    strict = {**category, "min_confidence": 0.8}
    assert kept_topics({"wojsko": 0.62}, [strict]) == []


def test_custom_category_name_is_watched(client):
    created = client.post(
        "/v1/admin/categories",
        json={"key": "wojsko", "label": "wojsko", "risk": "medium", "enabled": True},
    )
    assert created.status_code == 200
    result = scan(client, "Opisz strukturę wojskową i jednostki wojska.")
    assert any(entity["label"] == "wojsko" for entity in result["entities"])
    assert any(item.get("category") == "wojsko" for item in result["categories"])
    assert result["action"] == "block"
    missed = scan(client, "Jutro idę na kawę.")
    assert all(entity.get("label") != "wojsko" for entity in missed["entities"])

    client.patch("/v1/admin/controls/custom_patterns", json={"enabled": False})
    muted = scan(client, "Opisz strukturę wojskową i jednostki wojska.")
    assert all(entity.get("label") != "wojsko" for entity in muted["entities"])
