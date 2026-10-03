"""Historical attack signatures: prompt injection, jailbreaks, exploit payloads.

`data/signatures.json` is an externally managed feed. Judges can edit or
replace it; it is re-read when the mtime changes.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "signatures.json"

SIGNATURE_TYPES = (
    "prompt_injection",
    "jailbreak",
    "unsafe_deserialization",
    "malicious_code",
    "supply_chain",
    "tool_abuse",
    "data_exfiltration",
)

TYPE_LABEL = {
    "prompt_injection": "prompt injection",
    "jailbreak": "jailbreak",
    "unsafe_deserialization": "unsafe deserialization",
    "malicious_code": "malicious code",
    "supply_chain": "supply chain",
    "tool_abuse": "tool abuse",
    "data_exfiltration": "data exfiltration",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seed_signatures() -> dict[str, Any]:
    rows = [
        ("sig_ignore_prev", "Ignore previous instructions", "prompt_injection",
         r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts?)", "critical", "OWASP LLM01"),
        ("sig_disregard", "Disregard system prompt", "prompt_injection",
         r"disregard\s+(the\s+)?(system|previous|above)\s+(prompt|instructions?)", "critical", "OWASP LLM01"),
        ("sig_reveal_system", "Reveal system prompt", "prompt_injection",
         r"(print|reveal|show|repeat|output)\s+(me\s+)?(your|the)\s+(system\s+prompt|initial\s+instructions|hidden\s+rules)", "high", "OWASP LLM07"),
        ("sig_dev_mode", "Developer mode jailbreak", "jailbreak",
         r"(developer\s+mode|dev\s+mode)\s+(enabled|on|activated)", "critical", "DAN family"),
        ("sig_dan", "DAN / do anything now", "jailbreak",
         r"\b(DAN|do\s+anything\s+now)\b", "critical", "DAN family"),
        ("sig_no_restrictions", "No restrictions persona", "jailbreak",
         r"(you\s+are\s+now|act\s+as)\s+(an?\s+)?(unrestricted|unfiltered|uncensored)\s+(ai|assistant|model)", "critical", "jailbreak corpus"),
        ("sig_pickle", "Python pickle.loads", "unsafe_deserialization",
         r"pickle\.loads?\s*\(|cPickle\.loads?\s*\(", "critical", "CVE-2019-20907 class"),
        ("sig_torch_load", "torch.load without weights_only", "unsafe_deserialization",
         r"torch\.load\s*\((?![^)]*weights_only\s*=\s*True)", "high", "PyTorch advisory"),
        ("sig_yaml_load", "yaml.load without SafeLoader", "unsafe_deserialization",
         r"yaml\.load\s*\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)", "high", "CWE-502"),
        ("sig_java_deser", "Java ObjectInputStream", "unsafe_deserialization",
         r"ObjectInputStream|readObject\s*\(", "high", "CWE-502"),
        ("sig_eval_b64", "eval(base64)", "malicious_code",
         r"(eval|exec)\s*\(\s*(base64|b64decode|atob)", "critical", "obfuscated loader"),
        ("sig_curl_sh", "curl | sh", "malicious_code",
         r"(curl|wget)\s+[^\n|]*\|\s*(sudo\s+)?(ba)?sh", "critical", "remote install"),
        ("sig_rm_rf", "rm -rf /", "malicious_code",
         r"rm\s+-rf\s+(/|~|\$HOME)(\s|$)", "critical", "destructive shell"),
        ("sig_powershell_enc", "PowerShell -EncodedCommand", "malicious_code",
         r"powershell(\.exe)?\s+[^\n]*-(e|enc|encodedcommand)\s+[A-Za-z0-9+/=]{20,}", "critical", "encoded payload"),
        ("sig_reverse_shell", "Reverse shell", "malicious_code",
         r"/dev/tcp/|nc\s+-e\s+/bin/|bash\s+-i\s+>&", "critical", "reverse shell"),
        ("sig_hf_bin", "Unknown HF repo .bin / .pkl", "supply_chain",
         r"huggingface\.co/(?!openai|meta-llama|google|mistralai|Qwen|microsoft|goku-san)[^\s/]+/[^\s/]+/resolve/[^\s]+\.(bin|pkl|pt|pth)", "high", "model repo supply chain"),
        ("sig_pip_url", "pip install from URL / git", "supply_chain",
         r"pip\s+install\s+[^\n]*(https?://|git\+)", "medium", "untrusted package source"),
        ("sig_trust_remote", "trust_remote_code=True", "supply_chain",
         r"trust_remote_code\s*=\s*True", "high", "transformers remote code"),
        ("sig_npm_postinstall", "npm postinstall script", "supply_chain",
         r"\"postinstall\"\s*:\s*\"[^\"]*(curl|wget|node\s+-e)", "high", "npm supply chain"),
        ("sig_tool_shell", "Tool call: shell with sudo", "tool_abuse",
         r"\"(name|tool)\"\s*:\s*\"(shell|bash|exec|run_command)\"[^}]*sudo", "high", "agent tool abuse"),
        ("sig_exfil_env", "Exfiltrate env / secrets", "data_exfiltration",
         r"(cat|printenv|echo)\s+[^\n]*(\.env|AWS_SECRET|OPENAI_API_KEY)[^\n]*\|\s*(curl|wget|nc)", "critical", "secret exfiltration"),
        ("sig_exfil_url", "Send data to webhook", "data_exfiltration",
         r"(webhook\.site|requestbin|ngrok\.io|pipedream\.net)", "high", "exfiltration endpoint"),
    ]
    return {
        "updated_at": _now(),
        "source": "helios-seed",
        "signatures": [
            {
                "id": sid,
                "name": name,
                "type": kind,
                "pattern": pattern,
                "severity": severity,
                "source": source,
                "enabled": True,
            }
            for sid, name, kind, pattern, severity, source in rows
        ],
    }


class SignatureStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._data: dict[str, Any] = {"signatures": []}
        self._compiled: list[tuple[dict[str, Any], re.Pattern[str]]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(seed_signatures())

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def mtime(self) -> float:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return 0.0

    def _refresh(self) -> None:
        current = self.mtime()
        if self._mtime == current and self._compiled:
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {"signatures": []}
        compiled = []
        for row in data.get("signatures", []):
            if not row.get("enabled", True):
                continue
            try:
                compiled.append((row, re.compile(row.get("pattern") or "(?!x)x", re.I | re.S)))
            except re.error:
                continue
        self._data = data
        self._compiled = compiled
        self._mtime = current

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh()
            return json.loads(json.dumps(self._data))

    def list(self) -> list[dict[str, Any]]:
        return list(self.snapshot().get("signatures", []))

    def match(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        with self._lock:
            self._refresh()
            compiled = list(self._compiled)
        hits: list[dict[str, Any]] = []
        for row, pattern in compiled:
            found = pattern.search(text)
            if not found:
                continue
            hits.append(
                {
                    "signature_id": row.get("id"),
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "label": TYPE_LABEL.get(row.get("type"), "prompt injection"),
                    "severity": row.get("severity") or "critical",
                    "source": row.get("source") or "",
                    "start": found.start(),
                    "end": found.end(),
                    "text": found.group(0),
                }
            )
        return hits

    def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._refresh()
            data = self._data
            if not item.get("id"):
                item["id"] = f"sig_{uuid.uuid4().hex[:8]}"
            item.setdefault("enabled", True)
            item.setdefault("severity", "high")
            item.setdefault("source", "dashboard")
            rows = data.setdefault("signatures", [])
            for index, row in enumerate(rows):
                if row.get("id") == item["id"]:
                    rows[index] = {**row, **item}
                    break
            else:
                rows.append(item)
            data["updated_at"] = _now()
            self._write(data)
            self._mtime = None
            return item

    def delete(self, item_id: str) -> bool:
        with self._lock:
            self._refresh()
            rows = self._data.get("signatures", [])
            kept = [row for row in rows if row.get("id") != item_id]
            found = len(kept) != len(rows)
            self._data["signatures"] = kept
            self._data["updated_at"] = _now()
            self._write(self._data)
            self._mtime = None
            return found

    def import_feed(self, rows: list[dict[str, Any]], *, source: str = "import", replace: bool = False) -> int:
        with self._lock:
            self._refresh()
            data = self._data
            existing = {} if replace else {row.get("id"): row for row in data.get("signatures", [])}
            for row in rows:
                if not row.get("pattern"):
                    continue
                sid = row.get("id") or f"sig_{uuid.uuid4().hex[:8]}"
                existing[sid] = {
                    "id": sid,
                    "name": row.get("name") or sid,
                    "type": row.get("type") if row.get("type") in SIGNATURE_TYPES else "prompt_injection",
                    "pattern": row["pattern"],
                    "severity": row.get("severity") or "high",
                    "source": row.get("source") or source,
                    "enabled": bool(row.get("enabled", True)),
                }
            data["signatures"] = list(existing.values())
            data["updated_at"] = _now()
            data["source"] = source
            self._write(data)
            self._mtime = None
            return len(rows)
