"""Scan a few English and Polish documents with the heuristic backend."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensitive_guard import SensitiveDataLayer

SAMPLES = [
    "Hi, I'm Priya Nair. Call me on +44 7700 900123 or email priya.nair@example.com.",
    "Anna Kowalska, tel +48 600 100 200, PESEL 44051401359, NIP 123-456-32-18.",
    "Charge card 4111111111111111 and send the receipt to finance@acme.example.",
    "export OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz012345",
    "Please refund the duplicate invoice from March or we will cancel.",
]


def main() -> None:
    layer = SensitiveDataLayer(backend="heuristic", locale="pl")
    for text in SAMPLES:
        scan = layer.scan(text)
        print("=" * 80)
        print(text)
        print(f"-> risk={scan.risk.value} action={scan.action.value} cats={[c.category.value for c in scan.categories]}")
        print(scan.redacted)
        for entity in scan.entities:
            print(f"   {entity.text!r:40} {entity.label:20} {entity.category.value:16} {entity.risk.value}")


if __name__ == "__main__":
    main()
