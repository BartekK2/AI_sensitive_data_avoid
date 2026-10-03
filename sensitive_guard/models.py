"""Public result types for the sensitive-data layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .taxonomy import (
    COLLAPSE,
    GateAction,
    RiskLevel,
    SensitivityCategory,
    legal_for,
    redact_token,
)


class Entity(BaseModel):
    start: int
    end: int
    text: str
    label: str
    score: float = Field(ge=0.0, le=1.0)
    category: SensitivityCategory
    risk: RiskLevel
    legal: str | None = None
    families: list[str] = Field(default_factory=list)
    source: str = "heuristic"

    @property
    def collapsed_label(self) -> str:
        return COLLAPSE.get(self.label, self.label)


class CategorySummary(BaseModel):
    category: SensitivityCategory
    count: int
    max_risk: RiskLevel
    labels: list[str]


class ScanResult(BaseModel):
    text: str
    entities: list[Entity] = Field(default_factory=list)
    categories: list[CategorySummary] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.NONE
    action: GateAction = GateAction.ALLOW
    document_type: str = "unknown"
    backend: str = "heuristic"
    candidates: int = 0
    redacted: str = ""
    policy: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_sensitive(self) -> bool:
        return self.risk is not RiskLevel.NONE

    def entities_by_category(self, category: SensitivityCategory) -> list[Entity]:
        return [entity for entity in self.entities if entity.category is category]


class ProtectResult(BaseModel):
    action: GateAction
    original: str
    outbound: str | None
    blocked_reason: str | None = None
    scan: ScanResult


def redact_text(
    text: str,
    entities: list[Entity],
    *,
    locale: str = "en",
    collapse: bool = False,
) -> str:
    import re

    join_gap = re.compile(r"[ \t\-/.]*")
    chunks: list[str] = []
    pos = 0
    last: str | None = None
    for entity in sorted(entities, key=lambda item: item.start):
        label = entity.collapsed_label if collapse else entity.label
        token = redact_token(entity.label, locale=locale)
        if collapse:
            token = label.upper()
        gap = text[pos:entity.start]
        if collapse and label == last and join_gap.fullmatch(gap):
            pos = entity.end
            continue
        chunks.extend([gap, f"[{token}]"])
        pos = entity.end
        last = label
    return "".join(chunks) + text[pos:]


def summarize_categories(entities: list[Entity]) -> list[CategorySummary]:
    from .taxonomy import RISK_ORDER

    grouped: dict[SensitivityCategory, list[Entity]] = {}
    for entity in entities:
        grouped.setdefault(entity.category, []).append(entity)

    summaries: list[CategorySummary] = []
    for category, group in grouped.items():
        labels = sorted({item.label for item in group})
        risk = max((item.risk for item in group), key=lambda level: RISK_ORDER[level])
        summaries.append(
            CategorySummary(
                category=category,
                count=len(group),
                max_risk=risk,
                labels=labels,
            )
        )
    summaries.sort(key=lambda item: (-RISK_ORDER[item.max_risk], -item.count, item.category.value))
    return summaries


def entity_from(
    *,
    start: int,
    end: int,
    text: str,
    label: str,
    score: float,
    families: list[str] | None = None,
    source: str = "heuristic",
) -> Entity:
    from .taxonomy import category_for, risk_for

    return Entity(
        start=start,
        end=end,
        text=text,
        label=label,
        score=max(0.0, min(1.0, score)),
        category=category_for(label),
        risk=risk_for(label),
        legal=legal_for(label),
        families=families or [],
        source=source,
    )
