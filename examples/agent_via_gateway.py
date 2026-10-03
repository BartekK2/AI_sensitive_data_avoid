"""How an internal agent talks to OpenAI through Helios Net Gate.

Set OPENAI_BASE_URL to the gate. The SDK still sends Authorization;
we only swap the host. PESEL / keys never leave the company network.
"""

from __future__ import annotations

import json
import os
import urllib.request

GATE = os.environ.get("HELIOS_GATE", "http://127.0.0.1:8080")


def chat(content: str, employee_id: str = "emp_anna") -> dict:
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": content}],
    }
    request = urllib.request.Request(
        f"{GATE}/net/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Employee-Id": employee_id,
            "Authorization": os.environ.get("OPENAI_API_KEY", "sk-demo"),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8", errors="replace"))


if __name__ == "__main__":
    import urllib.error

    print("clean:", chat("Wytłumacz czym jest sieć neuronowa."))
    print("pesel:", chat("pesel: 0828282, napisz podanie"))
