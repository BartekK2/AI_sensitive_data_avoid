"""Context and shape rules that beat a greedy phone regex / Laya mix-up."""

from __future__ import annotations

import re

from .finder import Candidate

# Cue must sit immediately before the span: "pesel: 0828282", "API-KEY to sk-..."
CUE_BEFORE = re.compile(
    r"(?ix)"
    r"(?P<cue>pesel|nip|regon|iban|ssn|passport|paszport|dow[oó]d|"
    r"api[-_\s]?key|apikey|access[-_\s]?token|secret(?:[-_\s]?key)?|"
    r"password|passwd|haslo|hasło|token)"
    r"\s*[:#=\-]?\s*(?:to|is|jest|=|:|-)?\s*$"
)

CUE_LABEL = {
    "pesel": "pesel",
    "nip": "nip",
    "regon": "regon",
    "iban": "iban",
    "ssn": "social security number",
    "passport": "passport number",
    "paszport": "passport number",
    "dowod": "id card number",
    "dowód": "id card number",
    "api-key": "api key",
    "api_key": "api key",
    "api key": "api key",
    "apikey": "api key",
    "access-token": "access token",
    "access_token": "access token",
    "access token": "access token",
    "secret": "api key",
    "secret-key": "api key",
    "secret_key": "api key",
    "secret key": "api key",
    "password": "password",
    "passwd": "password",
    "haslo": "password",
    "hasło": "password",
    "token": "access token",
}

LABELED_VALUES = [
    ("CTX_PESEL", re.compile(r"(?i)\bpesel\s*[:#=\-]?\s*([0-9][0-9 \-]{4,16}[0-9])")),
    ("CTX_NIP", re.compile(r"(?i)\bnip\s*[:#=\-]?\s*([0-9][0-9 \-]{6,16}[0-9])")),
    ("CTX_REGON", re.compile(r"(?i)\bregon\s*[:#=\-]?\s*(\d{9,14})")),
    (
        "CTX_API",
        re.compile(
            r"(?i)\b(?:api[-_\s]?key|apikey|access[-_\s]?token|secret(?:[-_\s]?key)?|token)\s*[:#=\-]?\s*"
            r"(?:to|is|jest)?\s*([^\s,;]{6,})"
        ),
    ),
    ("CTX_PASS", re.compile(r"(?i)\b(?:password|passwd|haslo|hasło)\s*[:#=\-]?\s*(\S{4,})")),
]

FAMILY_LABEL = {
    "CTX_PESEL": "pesel",
    "CTX_NIP": "nip",
    "CTX_REGON": "regon",
    "CTX_API": "api key",
    "CTX_PASS": "password",
    "API_KEY": "api key",
    "BEARER": "access token",
    "PRIVATE_KEY": "private key",
    "PASSWORD_ASSIGN": "password",
    "PESEL": "pesel",
    "NIP": "nip",
    "REGON": "regon",
    "IBAN": "iban",
    "EMAIL": "email address",
}

LABEL_PRIORITY = {
    "api key": 80,
    "access token": 80,
    "private key": 80,
    "password": 80,
    "pesel": 70,
    "nip": 68,
    "regon": 66,
    "credit card number": 65,
    "iban": 64,
    "social security number": 63,
    "passport number": 62,
    "id card number": 60,
    "email address": 50,
    "phone number": 25,
    "person name": 20,
}

SECRET_PREFIX = re.compile(
    r"^(?:sk-[A-Za-z0-9]{8,}|sk-proj-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{8,}|ghp_[A-Za-z0-9]{8,}|xox[baprs]-)"
)


def propose_labeled_spans(text: str) -> dict[tuple[int, int], list[str]]:
    out: dict[tuple[int, int], list[str]] = {}
    for name, rx in LABELED_VALUES:
        for match in rx.finditer(text):
            start, end = match.span(1)
            while end > start and text[end - 1] in " .,;:-":
                end -= 1
            if end > start:
                out.setdefault((start, end), []).append(name)
    return out


def cue_label(left: str) -> str | None:
    match = CUE_BEFORE.search(left or "")
    if not match:
        return None
    raw = re.sub(r"[\s_]+", "-", match.group("cue").lower())
    raw = raw.replace("ó", "o")
    return CUE_LABEL.get(raw) or CUE_LABEL.get(raw.replace("-", " "))


def looks_like_phone(text: str) -> bool:
    if any(ch.isalpha() for ch in text):
        return False
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 9 or len(digits) > 15:
        return False
    compact = text.strip()
    if compact.isdigit() and len(digits) == 11:
        return False
    if compact.startswith("+"):
        return True
    if any(sep in compact for sep in (" ", "-", "(", ")")):
        return True
    return len(digits) == 9 and digits[0] in "456789"


def looks_like_api_key(text: str) -> bool:
    compact = text.strip().strip("'\"")
    if SECRET_PREFIX.match(compact):
        return True
    if len(compact) >= 16 and any(ch.isalpha() for ch in compact) and any(ch.isdigit() for ch in compact):
        if re.search(r"(?i)(api|key|secret|token|sk-)", compact):
            return True
    return False


def looks_like_pesel(text: str) -> bool:
    digits = "".join(ch for ch in text if ch.isdigit())
    return text.strip().isdigit() and len(digits) == 11


def resolve_label(candidate: Candidate, left: str = "", right: str = "") -> tuple[str, float] | None:
    del right
    text = candidate.text
    families = set(candidate.families)
    hinted = cue_label(left)

    if hinted == "pesel" and sum(ch.isdigit() for ch in text) >= 6:
        return "pesel", 0.96
    if hinted == "api key" and len(text.strip()) >= 6:
        return "api key", 0.97
    if hinted == "access token" and len(text.strip()) >= 6:
        return "access token", 0.96
    if hinted == "password" and len(text.strip()) >= 4:
        return "password", 0.95
    if hinted in {"nip", "regon", "iban", "social security number", "passport number", "id card number"}:
        if any(ch.isdigit() for ch in text) or len(text) >= 6:
            return hinted, 0.93

    if families.intersection({"CTX_PESEL", "PESEL"}):
        return "pesel", 0.97
    if families.intersection({"CTX_API", "API_KEY"}):
        return "api key", 0.99
    if "BEARER" in families:
        return "access token", 0.98
    if "PRIVATE_KEY" in families:
        return "private key", 0.99
    if families.intersection({"CTX_PASS", "PASSWORD_ASSIGN"}) and not families.intersection({"CTX_API", "API_KEY"}):
        return "password", 0.97
    if "CTX_NIP" in families:
        return "nip", 0.94
    if "CTX_REGON" in families:
        return "regon", 0.9
    if "EMAIL" in families:
        return "email address", 0.99
    if "IBAN" in families and len(re.sub(r"\s+", "", text)) >= 15:
        return "iban", 0.95

    if looks_like_api_key(text):
        return "api key", 0.98
    if looks_like_pesel(text):
        return "pesel", 0.92
    return None
