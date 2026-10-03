"""Drop-in privacy gateway in front of any outbound LLM call."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensitive_guard import GateAction, SensitiveDataBlocked, SensitiveDataLayer


def fake_llm(prompt: str) -> str:
    return f"[llm] received {len(prompt)} chars: {prompt[:80]!r}"


def ask_model(layer: SensitiveDataLayer, user_text: str) -> str:
    protected = layer.protect(user_text, raise_on_block=True)
    assert protected.outbound is not None
    print(f"gate={protected.action.value}  outbound={protected.outbound}")
    return fake_llm(protected.outbound)


def main() -> None:
    layer = SensitiveDataLayer(backend="heuristic", locale="pl")

    print(ask_model(layer, "Summarize this ticket: login page is blank on Safari."))
    print(ask_model(layer, "Write a reply to anna.kowalska@example.com about the refund."))

    try:
        ask_model(layer, "Debug this key: sk-proj-abcdefghijklmnopqrstuvwxyz012345")
    except SensitiveDataBlocked as exc:
        print(f"blocked: {exc.result.blocked_reason}")
        print(f"(would have been action={GateAction.BLOCK.value})")


if __name__ == "__main__":
    main()
