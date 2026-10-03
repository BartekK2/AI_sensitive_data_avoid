"""Rule-based span classifier used when Laya weights are not loaded."""

from __future__ import annotations

from .cues import looks_like_phone, resolve_label
from .finder import Candidate, luhn_ok
from .taxonomy import NOT_PII


def classify_candidate(candidate: Candidate, left: str = "", right: str = "") -> tuple[str, float]:
    families = set(candidate.families)
    text = candidate.text

    forced = resolve_label(candidate, left=left, right=right)
    if forced:
        return forced

    if "EMAIL" in families:
        return "email address", 0.99
    if "IBAN" in families and len(text.replace(" ", "")) >= 15:
        return "iban", 0.95
    if "CARD" in families and luhn_ok(text):
        return "credit card number", 0.97
    if "SSN_DASH" in families:
        return "social security number", 0.94
    if "PL_ID_CARD" in families:
        return "id card number", 0.88
    if ("PHONE" in families or "PHONE_RUN" in families) and looks_like_phone(text):
        return "phone number", 0.9
    if "URLISH" in families:
        return "web address", 0.93
    if "PL_POSTCODE" in families:
        return "postal code", 0.92
    if "AGE_PHRASE" in families:
        return "age", 0.9
    if "TITLE_GAZETTEER" in families and " " not in text.strip("."):
        return "title", 0.8
    if "GENDER_GAZETTEER" in families:
        return "gender", 0.75
    if "SEX_GAZETTEER" in families and len(text) > 1:
        return "sex", 0.7

    date_families = families.intersection(
        {"DATE_ISO", "DATE_NUMERIC", "DATE_WORDY", "DATE_WORDY_REV", "DATE_MONTH_SLASH"}
    )
    if date_families:
        if date_families <= {"DATE_WORDY", "DATE_WORDY_REV"} and not any(ch.isdigit() for ch in text):
            return NOT_PII, 1.0
        return "date", 0.85
    if "TIME" in families:
        return "time", 0.7
    if "ADDRESS_KEYWORD" in families:
        return "street", 0.72
    if families.intersection({"POSTCODE_UK", "POSTCODE_CA"}):
        return "postal code", 0.8

    if "CAPS_RUN" in families:
        parts = [part for part in text.replace("-", " ").split() if part]
        if 2 <= len(parts) <= 3 and all(
            part[:1].isupper() and part[1:].islower() and part.isalpha()
            for part in parts
        ):
            return "person name", 0.62

    return NOT_PII, 1.0


def heuristic_probs(candidate: Candidate, left: str = "", right: str = "") -> dict[str, float]:
    label, score = classify_candidate(candidate, left=left, right=right)
    if label == NOT_PII:
        return {NOT_PII: 1.0}
    return {label: score, NOT_PII: max(0.0, 1.0 - score)}
