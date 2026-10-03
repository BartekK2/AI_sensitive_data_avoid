"""Candidate span finder.

The core regex families and capitalised-run logic follow the training-time
finder from `goku-san/laya-experts` (Apache-2.0, `demo/pii_demo.py`). The
Laya PII expert only sees spans shaped the way it was trained.

Extra families (PESEL, NIP, IBAN, API keys, …) are layered on top. They
never change the original proposals — they only add more candidates.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
    "|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
SEX_WORDS = "male|female|man|woman|boy|girl|other|M|F|O|X"
GENDER_WORDS = (
    "non-binary|nonbinary|two-spirit|twospirit|transgender|trans|intersex|agender|androgynous|"
    "bigender|genderqueer|genderfluid|cisgender|cis|not specified|polygender|pangender|neutrois|"
    "demiboy|demigirl"
)
TITLE_WORDS = (
    "mr|mrs|ms|miss|mx|mister|madame|madam|master|dr|doctor|prof|professor|sir|dame|lord|lady|"
    "rev|reverend|hon|honourable|mayor|mayoress|captain|capt|sgt|officer"
)
ADDRESS_WORDS = r"Apt|Apt\.|Apartment|Suite|Ste|Unit|Flat|Block|Blk|Floor|Level|Room|Rm|#"

FAMILIES: dict[str, str] = {
    "EMAIL": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    "DATE_ISO": r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?",
    "DATE_NUMERIC": r"\b\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}\b",
    "DATE_WORDY": (
        rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?(?:{MONTHS})\.?"
        rf"(?:\s+\d{{1,2}}(?:st|nd|rd|th)?)?(?:,?\s*\d{{4}})?\b"
    ),
    "DATE_WORDY_REV": rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?\b",
    "TIME": r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap]\.?[Mm]\.?)?",
    "CARD": r"\b(?:\d{4}[ \-]?){3}\d{1,4}\b",
    "PHONE": r"(?:\+\d{1,3}[ .\-]?)?(?:\(\d{1,4}\)[ .\-]?)?\d{2,5}(?:[ .\-]\d{2,6}){1,4}",
    "PHONE_RUN": r"\+?\d[\d ().\-]{7,}\d",
    "ALNUM_ID": r"\b(?=[A-Za-z0-9\-]*\d)(?=[A-Za-z0-9\-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9\-]{4,}\b",
    "POSTCODE_UK": r"\b[A-Z]{1,2}\d{1,2}[A-Z]?[ ]?\d[A-Z]{2}\b",
    "POSTCODE_NUM": r"\b\d{4,6}(?:-\d{4})?\b",
    "BARE_INT": r"\b\d{1,15}\b",
    "SEX_GAZETTEER": rf"\b(?:{SEX_WORDS})\b",
    "GENDER_GAZETTEER": rf"\b(?:{GENDER_WORDS})\b",
    "ADDRESS_KEYWORD": rf"\b(?:{ADDRESS_WORDS})\s*[A-Za-z0-9\-]+\b",
    "AGE_PHRASE": r"\b\d{1,3}(?=[ \-]*(?:years?[ \-]old|yo\b|y/o\b))",
    "DATE_MONTH_SLASH": rf"\b(?:{MONTHS})[/\-]\d{{1,4}}\b",
    "SSN_DASH": r"\b\d{3}-\d{2}-\d{4}\b",
    "POSTCODE_CA": r"\b[A-Z]\d[A-Z](?:[ ]?\d[A-Z]\d)?\b",
    "TITLE_GAZETTEER": rf"\b(?:{TITLE_WORDS})\b\.?",
    "URLISH": r"\b(?:https?://|www\.)[^\s,;]+",
}

EXTRA_FAMILIES: dict[str, str] = {
    "PESEL": r"(?<![0-9])\d{11}(?![0-9])",
    "NIP": r"\b\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}\b",
    "REGON": r"\b\d{9}(?:\d{5})?\b",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b",
    "API_KEY": (
        r"\b(?:sk-[A-Za-z0-9]{10,}|sk-proj-[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{12,}|"
        r"ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
    "BEARER": r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b",
    "PRIVATE_KEY": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "PASSWORD_ASSIGN": r"(?i)\b(?:password|passwd|pwd|hasło|haslo)\s*[:=]\s*\S+",
    "PL_POSTCODE": r"\b\d{2}-\d{3}\b",
    "PL_ID_CARD": r"\b[A-Z]{3}\s?\d{6}\b",
}

_CASE_INSENSITIVE = {"SEX_GAZETTEER", "GENDER_GAZETTEER", "TITLE_GAZETTEER", "URLISH", "PASSWORD_ASSIGN"}
COMPILED = {
    name: re.compile(pattern, re.IGNORECASE if name in _CASE_INSENSITIVE else 0)
    for name, pattern in FAMILIES.items()
}
EXTRA_COMPILED = {
    name: re.compile(pattern, re.IGNORECASE if name in _CASE_INSENSITIVE else 0)
    for name, pattern in EXTRA_FAMILIES.items()
}

WORD_TOKEN = re.compile(r"\w[\w'’.\-]*", re.UNICODE)
CAPS_MAX_RUN = 5
PARTICLES = {
    "van", "von", "de", "del", "della", "der", "den", "da", "di", "du", "dos", "das",
    "al", "el", "bin", "binti", "binte", "ibn", "bint", "la", "le", "ter", "ten",
    "op", "af", "av", "mac", "mc", "st", "y", "e", "of", "ap", "abu",
}

DOC_TYPES: list[tuple[str, str]] = [
    ("email", r"\b(?:subject:|dear |regards,|sincerely,|unsubscribe|inbox|temat:|pozdrawiam)\b"),
    ("medical record", r"\b(?:patient|diagnos|clinic|prescri|symptom|therap|dosage|medical record|pacjent|rozpoznanie|recept)\b"),
    ("support ticket", r"\b(?:ticket|case number|support|helpdesk|issue id|resolved by)\b"),
    ("legal document", r"\b(?:hereby|pursuant|agreement|clause|plaintiff|defendant|contract|liabilit|umowa|klauzul)\b"),
    ("hr record", r"\b(?:employee|payroll|onboard|salary|performance review|hr department|hiring|pracownik|wynagrodzen)\b"),
    ("financial record", r"\b(?:invoice|payment|account balance|transaction|billing|statement|loan|faktura|przelew|rachunek)\b"),
    ("form or application", r"\b(?:application|form|please fill|registration|submit the|applicant|wniosek|formularz)\b"),
    ("message thread", r"\b(?:posted|reply|thread|forum|comment|@\w+|chat)\b"),
]
DOC_TYPE_RX = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in DOC_TYPES]

CONTEXT_CHARS = 400
SECRET_FAMILIES = frozenset({"API_KEY", "BEARER", "PRIVATE_KEY", "PASSWORD_ASSIGN"})
PL_ID_FAMILIES = frozenset({"PESEL", "NIP", "REGON", "PL_ID_CARD", "PL_POSTCODE"})
FINANCIAL_FAMILIES = frozenset({"IBAN", "CARD"})


@dataclass(frozen=True)
class Candidate:
    start: int
    end: int
    text: str
    families: tuple[str, ...]

    @property
    def is_secret(self) -> bool:
        return bool(SECRET_FAMILIES.intersection(self.families))

    @property
    def is_pl_id(self) -> bool:
        return bool(PL_ID_FAMILIES.intersection(self.families))


def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
    while end > start and text[end - 1] in " .,;:-":
        end -= 1
    if end <= start:
        return None
    return start, end


def propose_spans(text: str, max_run: int = CAPS_MAX_RUN, extra: bool = True) -> dict[tuple[int, int], list[str]]:
    """Character spans -> detector families that proposed each."""
    out: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
    for name, rx in COMPILED.items():
        for match in rx.finditer(text):
            trimmed = _trim(text, *match.span())
            if trimmed:
                out[trimmed].append(name)
    if extra:
        for name, rx in EXTRA_COMPILED.items():
            for match in rx.finditer(text):
                trimmed = _trim(text, *match.span())
                if trimmed:
                    out[trimmed].append(name)
        from .cues import propose_labeled_spans

        for span, names in propose_labeled_spans(text).items():
            out[span].extend(names)

    toks: list[tuple[int, int, str]] = []
    for match in WORD_TOKEN.finditer(text):
        word = match.group(0)
        if word[:1].isupper():
            kind = "cap"
        elif word.lower().strip(".") in PARTICLES:
            kind = "particle"
        else:
            kind = None
        if kind:
            toks.append((match.start(), match.end(), kind))

    runs: list[list[tuple[int, int, str]]] = []
    for token in toks:
        if runs and text[runs[-1][-1][1]:token[0]].strip() in ("", "-"):
            runs[-1].append(token)
        else:
            runs.append([token])

    for run in runs:
        if not any(token[2] == "cap" for token in run):
            continue
        for i in range(len(run)):
            if run[i][2] == "particle":
                continue
            for j in range(i, min(i + max_run, len(run))):
                if run[j][2] == "particle":
                    continue
                trimmed = _trim(text, run[i][0], run[j][1])
                if trimmed:
                    out[trimmed].append("CAPS_RUN" if j > i else "CAPS_SINGLE")
    return dict(out)


def doc_type(text: str) -> str:
    best, best_n = "unknown", 0
    for name, rx in DOC_TYPE_RX:
        count = len(rx.findall(text))
        if count > best_n:
            best, best_n = name, count
    return best


def build_states(text: str, region: str = "PL") -> list[tuple[Candidate, dict]]:
    """One Laya state per candidate, in the exact key order the PII expert was trained on."""
    document = doc_type(text)
    rows: list[tuple[Candidate, dict]] = []
    for (start, end), families in sorted(propose_spans(text).items()):
        candidate = Candidate(start, end, text[start:end], tuple(families))
        rows.append((
            candidate,
            {
                "document_type": document,
                "language": "English",
                "region": region,
                "left": text[max(0, start - CONTEXT_CHARS):start],
                "span": text[start:end],
                "right": text[end:end + CONTEXT_CHARS],
            },
        ))
    return rows


def pesel_checksum_ok(value: str) -> bool:
    digits = [ch for ch in value if ch.isdigit()]
    if len(digits) != 11:
        return False
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    total = sum(int(digit) * weight for digit, weight in zip(digits[:10], weights))
    return (10 - (total % 10)) % 10 == int(digits[10])


def nip_checksum_ok(value: str) -> bool:
    digits = [ch for ch in value if ch.isdigit()]
    if len(digits) != 10:
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    total = sum(int(digit) * weight for digit, weight in zip(digits[:9], weights))
    check = total % 11
    return check != 10 and check == int(digits[9])


def luhn_ok(value: str) -> bool:
    digits = [int(ch) for ch in value if ch.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0
