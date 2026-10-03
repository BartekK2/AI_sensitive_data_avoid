from pathlib import Path

from sensitive_guard.workspace import WorkspaceStore, apply_workspace_policy, entity_whitelisted, seed


def test_whitelist_and_role(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "ws.json")
    store._write(seed())
    email = {"text": "anna.nowak@helios.pl", "label": "email address", "category": "contact", "risk": "medium"}
    rule = entity_whitelisted(email, store.list_collection("whitelist"))
    assert rule is not None

    hr = store.employee_by_id_or_email("emp_magda", None)
    kept, skipped = apply_workspace_policy(
        [{"text": "Jan Kowalski", "label": "person name", "category": "person_name", "risk": "medium"}],
        store=store,
        employee=hr,
    )
    assert kept == []
    assert skipped[0]["skipped_by"] == "role"


def test_pesel_not_whitelisted(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "ws.json")
    store._write(seed())
    worker = store.employee_by_id_or_email("emp_anna", None)
    kept, _skipped = apply_workspace_policy(
        [{"text": "44051401359", "label": "pesel", "category": "government_id", "risk": "critical"}],
        store=store,
        employee=worker,
    )
    assert len(kept) == 1
