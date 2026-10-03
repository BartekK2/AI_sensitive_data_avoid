"""Sensitive-data layer: find, classify, categorize, redact or block."""

from __future__ import annotations

import os
import re
from typing import Literal

from .cues import LABEL_PRIORITY, looks_like_phone, resolve_label
from .finder import Candidate, build_states, doc_type
from .heuristic import heuristic_probs
from .laya_backend import LayaPiiClassifier, LayaPolicyClassifier, laya_available
from .models import Entity, ProtectResult, ScanResult, entity_from, redact_text, summarize_categories
from .taxonomy import (
    ACTION_ORDER,
    NOT_PII,
    GateAction,
    RiskLevel,
    action_for_risk,
    max_risk,
)

BackendName = Literal["auto", "laya", "heuristic"]
JOIN_GAP = re.compile(r"[ \t\-/.]*")


class SensitiveDataBlocked(RuntimeError):
    def __init__(self, result: ProtectResult) -> None:
        super().__init__(result.blocked_reason or "sensitive data blocked")
        self.result = result


class SensitiveDataLayer:
    """Gateway in front of an LLM or any outbound text sink.

    Pipeline:
      1. Rule-based finder proposes candidate spans (same families as Laya PII training).
      2. Laya Experts · pii classifies each span, or a heuristic fallback does.
      3. Secrets / validated Polish IDs are kept even if the PII head says ``not pii``.
      4. Nested spans are resolved; document risk and gate action are derived.
      5. Optional Laya Router adds a document-level policy vote.
    """

    def __init__(
        self,
        backend: BackendName = "auto",
        *,
        device: str | None = None,
        region: str = "PL",
        locale: str = "pl",
        threshold: float = 0.5,
        strict: bool = False,
        use_policy: bool = False,
        policy_model: str | None = None,
        batch_size: int = 16,
    ) -> None:
        self.region = region
        self.locale = locale
        self.threshold = threshold
        self.strict = strict
        self.use_policy = use_policy
        self.device = device or os.getenv("SENSITIVE_GUARD_DEVICE")
        self.batch_size = batch_size
        self._pii: LayaPiiClassifier | None = None
        self._policy: LayaPolicyClassifier | None = None
        self.backend = self._resolve_backend(backend)
        if self.backend == "laya":
            self._pii = LayaPiiClassifier(device=self.device, batch_size=batch_size)
        if use_policy:
            if not laya_available():
                raise RuntimeError("Document policy requires the `laya` package. pip install laya")
            self._policy = LayaPolicyClassifier(device=self.device, model=policy_model)

    def _resolve_backend(self, backend: BackendName) -> str:
        if backend == "heuristic":
            return "heuristic"
        if backend == "laya":
            if not laya_available():
                raise RuntimeError("Laya backend requested but `laya` is not installed. pip install laya")
            return "laya"
        return "laya" if laya_available() else "heuristic"

    def scan(
        self,
        text: str,
        *,
        threshold: float | None = None,
        region: str | None = None,
        locale: str | None = None,
        collapse: bool = False,
    ) -> ScanResult:
        if not text:
            return ScanResult(text=text, redacted=text, backend=self.backend)

        cut = self.threshold if threshold is None else threshold
        region = region or self.region
        locale = locale or self.locale
        rows = build_states(text, region=region)
        states = [state for _, state in rows]
        probs = self._score(rows, states)

        kept: list[tuple[int, float, bool, int, Entity]] = []
        for (candidate, state), distribution in zip(rows, probs):
            entity = self._decide(candidate, state, distribution, cut)
            if entity is None:
                continue
            multi_word = bool(candidate.families) and all(family == "CAPS_RUN" for family in candidate.families)
            kept.append((
                -LABEL_PRIORITY.get(entity.label, 10),
                -round(entity.score, 1),
                multi_word,
                candidate.start - candidate.end,
                entity,
            ))

        chosen: list[Entity] = []
        for *_, entity in sorted(kept, key=lambda item: item[:4]):
            if all(entity.end <= other.start or entity.start >= other.end for other in chosen):
                chosen.append(entity)
        chosen.sort(key=lambda item: item.start)
        merged = self._merge_adjacent(text, chosen)

        risk = max_risk([entity.risk for entity in merged])
        action = action_for_risk(risk, strict=self.strict)
        policy: dict = {}
        if self._policy is not None:
            policy = self._policy.classify(text, lang="pl" if locale.startswith("pl") else None)
            action = self._merge_action(action, policy)

        return ScanResult(
            text=text,
            entities=merged,
            categories=summarize_categories(merged),
            risk=risk,
            action=action,
            document_type=doc_type(text),
            backend=self.backend,
            candidates=len(rows),
            redacted=redact_text(text, merged, locale=locale, collapse=collapse),
            policy=policy,
        )

    def protect(
        self,
        text: str,
        *,
        raise_on_block: bool = False,
        **scan_kwargs,
    ) -> ProtectResult:
        scan = self.scan(text, **scan_kwargs)
        if scan.action is GateAction.BLOCK:
            result = ProtectResult(
                action=GateAction.BLOCK,
                original=text,
                outbound=None,
                blocked_reason=self._block_reason(scan),
                scan=scan,
            )
            if raise_on_block:
                raise SensitiveDataBlocked(result)
            return result
        outbound = scan.redacted if scan.action is GateAction.REDACT else text
        return ProtectResult(
            action=scan.action,
            original=text,
            outbound=outbound,
            scan=scan,
        )

    def _score(self, rows: list[tuple[Candidate, dict]], states: list[dict]) -> list[dict[str, float]]:
        if self._pii is None:
            return [heuristic_probs(candidate, left=state.get("left", ""), right=state.get("right", "")) for candidate, state in rows]
        return self._pii.score(states)

    def _decide(
        self,
        candidate: Candidate,
        state: dict,
        probs: dict[str, float],
        threshold: float,
    ) -> Entity | None:
        override = resolve_label(candidate, left=state.get("left", ""), right=state.get("right", ""))
        if override is None and "phone number" in probs:
            if not looks_like_phone(candidate.text):
                probs = {key: value for key, value in probs.items() if key != "phone number"}
                if not probs:
                    probs = {NOT_PII: 1.0}
        if override is not None:
            label, score = override
            return entity_from(
                start=candidate.start,
                end=candidate.end,
                text=candidate.text,
                label=label,
                score=score,
                families=list(candidate.families),
                source=f"{self.backend}+rule",
            )

        pii_score = 1.0 - float(probs.get(NOT_PII, 0.0))
        if pii_score < threshold:
            return None
        label = max((key for key in probs if key != NOT_PII), key=probs.get, default=NOT_PII)
        if label == NOT_PII:
            return None
        if label == "phone number" and not looks_like_phone(candidate.text):
            return None
        return entity_from(
            start=candidate.start,
            end=candidate.end,
            text=candidate.text,
            label=label,
            score=pii_score,
            families=list(candidate.families),
            source=self.backend,
        )

    def _merge_adjacent(self, text: str, entities: list[Entity]) -> list[Entity]:
        merged: list[Entity] = []
        for entity in entities:
            prev = merged[-1] if merged else None
            if prev and prev.label == entity.label and JOIN_GAP.fullmatch(text[prev.end:entity.start]):
                merged[-1] = entity_from(
                    start=prev.start,
                    end=entity.end,
                    text=text[prev.start:entity.end],
                    label=entity.label,
                    score=min(prev.score, entity.score),
                    families=sorted(set(prev.families + entity.families)),
                    source=entity.source,
                )
            else:
                merged.append(entity)
        return merged

    def _merge_action(self, derived: GateAction, policy: dict) -> GateAction:
        voted = policy.get("action")
        try:
            policy_action = GateAction(voted)
        except ValueError:
            return derived
        return policy_action if ACTION_ORDER[policy_action] > ACTION_ORDER[derived] else derived

    def _block_reason(self, scan: ScanResult) -> str:
        critical = [entity for entity in scan.entities if entity.risk is RiskLevel.CRITICAL]
        if critical:
            labels = ", ".join(sorted({entity.label for entity in critical}))
            return f"Blocked: critical sensitive data ({labels})"
        if scan.policy.get("action") == "block":
            return "Blocked: Laya document policy voted block"
        return "Blocked: high-risk sensitive data"


def scan_text(text: str, **kwargs) -> ScanResult:
    backend = kwargs.pop("backend", "auto")
    return SensitiveDataLayer(backend=backend).scan(text, **kwargs)
