"""Pytest plugin: write the last run summary so the dashboard can show it.

The gateway reads ``data/last_pytest.json`` for ``/health`` and the posture
page. Judges run ``pytest`` and the status bar updates on the next poll.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "last_pytest.json"
_STARTED = time.monotonic()


def pytest_sessionstart(session):  # type: ignore[no-untyped-def]
    global _STARTED
    _STARTED = time.monotonic()


def pytest_sessionfinish(session, exitstatus):  # type: ignore[no-untyped-def]
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    stats = reporter.stats
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", [])) + len(stats.get("error", []))
    skipped = len(stats.get("skipped", []))
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "exit_status": int(exitstatus),
        "duration_s": round(time.monotonic() - _STARTED, 2),
    }
    try:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass
