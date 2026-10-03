"""Custom categories as Laya topics.

The category name is a question ("does this text concern wojsko?"), not a word list.
Related things (czołg, żołnierz) score below the exact word, and the category slider
is the minimum confidence that still counts.
"""

from __future__ import annotations

import os
import threading
from typing import Any

_lock = threading.Lock()
_router: Any = None
_failed = False

DEFAULT_MIN_CONFIDENCE = 0.35


def topics_enabled() -> bool:
    flag = os.environ.get("SENSITIVE_GUARD_TOPICS", "1").strip().lower()
    return flag not in {"0", "false", "off", "no"}


def min_confidence_of(category: dict[str, Any]) -> float:
    try:
        value = float(category.get("min_confidence"))
    except (TypeError, ValueError):
        value = DEFAULT_MIN_CONFIDENCE
    if value != value:  # NaN
        value = DEFAULT_MIN_CONFIDENCE
    return min(0.95, max(0.05, value))


def _noul(answer: Any) -> float:
    if not isinstance(answer, dict):
        return 0.0
    value = answer.get("noul")
    if value is None:
        value = answer.get("confidence") or answer.get("answer_confidence") or 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def kept_topics(scores: dict[str, float], categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Categories whose Laya score clears that category's own slider."""
    hits: list[dict[str, Any]] = []
    for category in categories:
        if not category.get("enabled", True) or category.get("builtin"):
            continue
        key = category.get("key") or ""
        if not key:
            continue
        score = float(scores.get(key) or 0.0)
        floor = min_confidence_of(category)
        if score < floor:
            continue
        hits.append({**category, "key": key, "confidence": score, "min_confidence": floor})
    return hits


def _router_instance() -> Any:
    global _router, _failed
    if not topics_enabled() or _failed:
        return None
    if _router is not None:
        return _router
    with _lock:
        if _router is None and not _failed:
            try:
                os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
                from laya import Router

                _router = Router(max_loaded=1)
            except Exception:
                _failed = True
                return None
    return _router


def _question(label: str) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": "What is the message about?",
        "criteria": {
            "topic": (
                f"about {label}, including closely related objects, roles, equipment, "
                "places and activities, even when that word is absent"
            ),
            "other": "about something else",
        },
    }


def _topic_score(answer: Any) -> float:
    if not isinstance(answer, dict):
        return 0.0
    probs = answer.get("probabilities")
    if isinstance(probs, dict) and "topic" in probs:
        try:
            return float(probs["topic"])
        except (TypeError, ValueError):
            return 0.0
    return _noul(answer)


def topic_matches(text: str, categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    custom = [
        category
        for category in categories
        if category.get("enabled", True) and not category.get("builtin") and (category.get("label") or category.get("key"))
    ]
    if not text.strip() or not custom or not topics_enabled():
        return []
    router = _router_instance()
    if router is None:
        return []
    questions: dict[str, dict[str, str]] = {}
    owners: dict[str, dict[str, Any]] = {}
    for index, category in enumerate(custom):
        qid = f"topic_{index}"
        label = (category.get("label") or category.get("key") or "").strip()
        questions[qid] = _question(label)
        owners[qid] = category
    try:
        result = router.predict({"message": text}, questions, model="multilingual", lang="pl")
    except Exception:
        return []
    answers = (result or {}).get("answers") or {}
    scores = {
        (owners[qid].get("key") or ""): _topic_score(answers.get(qid))
        for qid in owners
        if owners[qid].get("key")
    }
    return kept_topics(scores, custom)
