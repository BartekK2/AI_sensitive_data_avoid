"""Optional Laya backends: span PII expert and document-level policy Router."""

from __future__ import annotations

from typing import Any

from .taxonomy import LAYA_INSTRUCTIONS, LAYA_LABELS

PII_REPO = "goku-san/laya-experts"
PII_SUBFOLDER = "pii"

POLICY_QUESTIONS: dict[str, dict[str, Any]] = {
    "contains_sensitive": {
        "type": "noul",
        "instructions": (
            "Does this text contain personal, financial, medical, or secret data "
            "that should not be sent to an external model unchanged?"
        ),
    },
    "sensitivity_class": {
        "type": "choice",
        "instructions": "What is the primary kind of sensitive information in this text?",
        "criteria": {
            "none": "no personal or confidential data",
            "pii": "names, contact details, or personal identifiers",
            "financial": "payment cards, bank accounts, invoices with identifiers",
            "health": "medical, diagnosis, treatment, or patient data",
            "credentials": "passwords, API keys, tokens, or secrets",
            "legal": "contracts or government identifiers in a legal context",
        },
    },
    "risk": {
        "type": "score",
        "instructions": "How risky is it to send this text to a third-party LLM?",
        "criteria": ["safe to send", "review before sending", "must redact", "must block"],
    },
    "action": {
        "type": "choice",
        "instructions": "What should a privacy gateway do with this text?",
        "criteria": {
            "allow": "safe, no sensitive data",
            "redact": "contains PII that can be masked and then forwarded",
            "block": "contains secrets or high-risk identifiers that must not leave",
        },
    },
}


def laya_available() -> bool:
    try:
        import laya  # noqa: F401
    except ImportError:
        return False
    return True


class LayaPiiClassifier:
    """Fine-tuned Laya Experts · pii (22-way span classifier)."""

    def __init__(
        self,
        model: str = PII_REPO,
        subfolder: str | None = PII_SUBFOLDER,
        device: str | None = None,
        batch_size: int = 16,
    ) -> None:
        import laya

        self.agent = laya.Agent(model, subfolder=subfolder, device=device)
        self.batch_size = batch_size
        self.question = {
            "type": "choice",
            "instructions": LAYA_INSTRUCTIONS,
            "criteria": LAYA_LABELS,
        }

    def score(self, states: list[dict]) -> list[dict[str, float]]:
        if not states:
            return []
        try:
            return self._score_batched(states)
        except Exception:
            return self._score_predict(states)

    def _score_predict(self, states: list[dict]) -> list[dict[str, float]]:
        out: list[dict[str, float]] = []
        for state in states:
            answer = self.agent.predict(state, {"label": self.question})["answers"]["label"]
            probs = answer.get("probabilities")
            if isinstance(probs, dict) and probs:
                out.append({key: float(value) for key, value in probs.items()})
            else:
                choice = str(answer.get("choice", LAYA_LABELS[0]))
                out.append({choice: 1.0})
        return out

    def _score_batched(self, states: list[dict]) -> list[dict[str, float]]:
        import numpy as np
        import torch
        from laya.common import QTYPES, build_sequence, collate_items, temp_bucket

        agent = self.agent
        max_len = agent.cfg.get("max_len", 512)
        head_max_len = agent.cfg.get("head_max_len", 192)
        question = agent._to_internal(self.question)
        qtype = QTYPES["choice"]
        temperature = agent.temperature_by_options.get(
            temp_bucket(qtype, len(LAYA_LABELS)),
            agent.temperature[qtype],
        )
        out: list[dict[str, float]] = []
        with torch.no_grad():
            for start in range(0, len(states), self.batch_size):
                items = []
                for state in states[start:start + self.batch_size]:
                    seq, markers = build_sequence(agent.tok, state, question, max_len, head_max_len)
                    items.append({"ids": seq, "markers": markers, "qtype": qtype})
                batch = collate_items([items], agent.tok.pad_token_id)
                tensors = (
                    batch[key].to(agent.device)
                    for key in ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")
                )
                enabled = agent.device.type == "cuda"
                with torch.autocast(device_type=agent.device.type, dtype=agent.dtype, enabled=enabled):
                    logits, _ = agent.model(*tensors)
                scaled = logits.float().cpu().numpy()[:, :len(LAYA_LABELS)] / temperature
                shifted = np.exp(scaled - scaled.max(axis=1, keepdims=True))
                shifted /= shifted.sum(axis=1, keepdims=True)
                out.extend(dict(zip(LAYA_LABELS, map(float, row))) for row in shifted)
        return out


class LayaPolicyClassifier:
    """Document-level typed decisions via Laya Router (Jev-compatible)."""

    def __init__(self, device: str | None = None, model: str | None = None) -> None:
        from laya import Router

        kwargs: dict[str, Any] = {}
        if device:
            kwargs["device"] = device
        self.router = Router(**kwargs)
        self.model = model

    def classify(self, text: str, lang: str | None = None) -> dict[str, Any]:
        result = self.router.predict(text, POLICY_QUESTIONS, model=self.model, lang=lang)
        answers = result.get("answers", {})
        action = answers.get("action", {})
        risk = answers.get("risk", {})
        klass = answers.get("sensitivity_class", {})
        contains = answers.get("contains_sensitive", {})
        return {
            "contains_sensitive": float(contains.get("noul", 0.0) or 0.0),
            "sensitivity_class": klass.get("choice"),
            "sensitivity_class_confidence": float(klass.get("confidence") or klass.get("answer_confidence") or 0.0),
            "risk_level": risk.get("score"),
            "risk_label": (risk.get("criteria") or [None] * 4)[int(round(float(risk.get("score") or 0)))]
            if isinstance(risk.get("score"), (int, float))
            else None,
            "action": action.get("choice"),
            "action_confidence": float(action.get("confidence") or action.get("answer_confidence") or 0.0),
            "routing": result.get("routing"),
        }
