"""PII taxonomy, GDPR-oriented categories, and risk policy.

The 22 span labels match `goku-san/laya-experts` (`pii/labels.json`) so the
fine-tuned Laya classifier sees the same answer set it was trained on.
"""

from __future__ import annotations

from enum import Enum

LAYA_INSTRUCTIONS = (
    "A candidate span of text was pulled out of a document, and is shown with the text either "
    "side of it. Which kind of personal data is the span itself, or is it not personal data at "
    "all? Judge the span, not the surrounding text."
)

NOT_PII = "not pii"

# Dataset-native labels used by Laya Experts · pii
LABEL_MAP: dict[str, str] = {
    "GIVENNAME": "given name",
    "SURNAME": "surname",
    "TITLE": "title",
    "GENDER": "gender",
    "SEX": "sex",
    "AGE": "age",
    "DATE": "date",
    "EMAIL": "email address",
    "TELEPHONENUM": "phone number",
    "SOCIALNUM": "social security number",
    "TAXNUM": "tax number",
    "IDCARDNUM": "id card number",
    "PASSPORTNUM": "passport number",
    "DRIVERLICENSENUM": "driver licence number",
    "CREDITCARDNUMBER": "credit card number",
    "STREET": "street",
    "BUILDINGNUM": "building number",
    "CITY": "city",
    "ZIPCODE": "postal code",
    "TIME": "time",
    "URL": "web address",
}

LAYA_LABELS: list[str] = list(LABEL_MAP.values()) + [NOT_PII]

# Extra labels used only by the hybrid layer (secrets / PL identifiers).
# They are never sent to the Laya PII head.
LAYER_LABELS: list[str] = [
    "person name",
    "pesel",
    "nip",
    "regon",
    "iban",
    "api key",
    "access token",
    "private key",
    "password",
]

COLLAPSE: dict[str, str] = {
    "given name": "person name",
    "surname": "person name",
    "person name": "person name",
    "title": "person name",
    "gender": "sex or gender",
    "sex": "sex or gender",
    "social security number": "government id number",
    "tax number": "government id number",
    "id card number": "government id number",
    "passport number": "government id number",
    "driver licence number": "government id number",
    "pesel": "government id number",
    "nip": "government id number",
    "regon": "government id number",
    "credit card number": "payment card number",
    "iban": "payment card number",
    "street": "street address",
    "building number": "street address",
    "age": "age",
    "date": "date",
    "email address": "email address",
    "phone number": "phone number",
    "city": "city",
    "postal code": "postal code",
    "time": "date",
    "web address": "web address",
    "api key": "secret",
    "access token": "secret",
    "private key": "secret",
    "password": "secret",
    NOT_PII: NOT_PII,
}


class SensitivityCategory(str, Enum):
    PERSON_NAME = "person_name"
    CONTACT = "contact"
    LOCATION = "location"
    GOVERNMENT_ID = "government_id"
    FINANCIAL = "financial"
    CREDENTIALS = "credentials"
    DEMOGRAPHIC = "demographic"
    TEMPORAL = "temporal"
    ONLINE = "online"
    HEALTH = "health"
    OTHER = "other"
    NONE = "none"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateAction(str, Enum):
    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"


LABEL_CATEGORY: dict[str, SensitivityCategory] = {
    "given name": SensitivityCategory.PERSON_NAME,
    "surname": SensitivityCategory.PERSON_NAME,
    "person name": SensitivityCategory.PERSON_NAME,
    "title": SensitivityCategory.PERSON_NAME,
    "email address": SensitivityCategory.CONTACT,
    "phone number": SensitivityCategory.CONTACT,
    "street": SensitivityCategory.LOCATION,
    "building number": SensitivityCategory.LOCATION,
    "city": SensitivityCategory.LOCATION,
    "postal code": SensitivityCategory.LOCATION,
    "social security number": SensitivityCategory.GOVERNMENT_ID,
    "tax number": SensitivityCategory.GOVERNMENT_ID,
    "id card number": SensitivityCategory.GOVERNMENT_ID,
    "passport number": SensitivityCategory.GOVERNMENT_ID,
    "driver licence number": SensitivityCategory.GOVERNMENT_ID,
    "pesel": SensitivityCategory.GOVERNMENT_ID,
    "nip": SensitivityCategory.GOVERNMENT_ID,
    "regon": SensitivityCategory.GOVERNMENT_ID,
    "credit card number": SensitivityCategory.FINANCIAL,
    "iban": SensitivityCategory.FINANCIAL,
    "api key": SensitivityCategory.CREDENTIALS,
    "access token": SensitivityCategory.CREDENTIALS,
    "private key": SensitivityCategory.CREDENTIALS,
    "password": SensitivityCategory.CREDENTIALS,
    "gender": SensitivityCategory.DEMOGRAPHIC,
    "sex": SensitivityCategory.DEMOGRAPHIC,
    "age": SensitivityCategory.DEMOGRAPHIC,
    "date": SensitivityCategory.TEMPORAL,
    "time": SensitivityCategory.TEMPORAL,
    "web address": SensitivityCategory.ONLINE,
    NOT_PII: SensitivityCategory.NONE,
}

LABEL_RISK: dict[str, RiskLevel] = {
    "api key": RiskLevel.CRITICAL,
    "access token": RiskLevel.CRITICAL,
    "private key": RiskLevel.CRITICAL,
    "password": RiskLevel.CRITICAL,
    "credit card number": RiskLevel.CRITICAL,
    "iban": RiskLevel.CRITICAL,
    "social security number": RiskLevel.CRITICAL,
    "pesel": RiskLevel.CRITICAL,
    "passport number": RiskLevel.HIGH,
    "id card number": RiskLevel.HIGH,
    "driver licence number": RiskLevel.HIGH,
    "tax number": RiskLevel.HIGH,
    "nip": RiskLevel.HIGH,
    "regon": RiskLevel.HIGH,
    "email address": RiskLevel.MEDIUM,
    "phone number": RiskLevel.MEDIUM,
    "given name": RiskLevel.MEDIUM,
    "surname": RiskLevel.MEDIUM,
    "person name": RiskLevel.MEDIUM,
    "street": RiskLevel.MEDIUM,
    "building number": RiskLevel.MEDIUM,
    "postal code": RiskLevel.MEDIUM,
    "age": RiskLevel.LOW,
    "date": RiskLevel.LOW,
    "time": RiskLevel.LOW,
    "city": RiskLevel.LOW,
    "title": RiskLevel.LOW,
    "gender": RiskLevel.LOW,
    "sex": RiskLevel.LOW,
    "web address": RiskLevel.LOW,
    NOT_PII: RiskLevel.NONE,
}

# GDPR / compliance hints for the hackathon pitch and audit trail.
LABEL_LEGAL: dict[str, str] = {
    "given name": "RODO art. 4 — dane identyfikujące",
    "surname": "RODO art. 4 — dane identyfikujące",
    "person name": "RODO art. 4 — dane identyfikujące",
    "title": "RODO art. 4 — dane identyfikujące",
    "email address": "RODO art. 4 — dane kontaktowe",
    "phone number": "RODO art. 4 — dane kontaktowe",
    "street": "RODO art. 4 — dane lokalizacyjne",
    "building number": "RODO art. 4 — dane lokalizacyjne",
    "city": "RODO art. 4 — dane lokalizacyjne",
    "postal code": "RODO art. 4 — dane lokalizacyjne",
    "social security number": "RODO art. 4 / PESEL — identyfikator krajowy",
    "pesel": "RODO art. 4 / ustawa o PESEL — identyfikator krajowy",
    "tax number": "dane podatkowe (NIP)",
    "nip": "dane podatkowe (NIP)",
    "regon": "dane rejestowe (REGON)",
    "id card number": "dokument tożsamości",
    "passport number": "dokument tożsamości",
    "driver licence number": "dokument tożsamości",
    "credit card number": "PCI-DSS — dane karty płatniczej",
    "iban": "dane finansowe — rachunek bankowy",
    "api key": "sekret / poświadczenie dostępu",
    "access token": "sekret / poświadczenie dostępu",
    "private key": "sekret kryptograficzny",
    "password": "sekret / poświadczenie dostępu",
    "gender": "RODO art. 9 — szczególna kategoria (płeć/tożsamość)",
    "sex": "RODO art. 9 — szczególna kategoria (płeć)",
    "age": "RODO art. 4 — dane demograficzne",
    "date": "RODO art. 4 — data (może identyfikować osobę)",
    "time": "RODO art. 4 — znacznik czasu",
    "web address": "RODO art. 4 — identyfikator online",
}

REDACT_EN: dict[str, str] = {
    "given name": "GIVEN NAME",
    "surname": "SURNAME",
    "person name": "PERSON",
    "title": "TITLE",
    "gender": "GENDER",
    "sex": "SEX",
    "age": "AGE",
    "date": "DATE",
    "email address": "EMAIL",
    "phone number": "PHONE",
    "social security number": "SSN",
    "tax number": "TAX ID",
    "id card number": "ID CARD",
    "passport number": "PASSPORT",
    "driver licence number": "DRIVER LICENCE",
    "credit card number": "CREDIT CARD",
    "street": "STREET",
    "building number": "BUILDING",
    "city": "CITY",
    "postal code": "POSTAL CODE",
    "time": "TIME",
    "web address": "URL",
    "pesel": "PESEL",
    "nip": "NIP",
    "regon": "REGON",
    "iban": "IBAN",
    "api key": "API KEY",
    "access token": "TOKEN",
    "private key": "PRIVATE KEY",
    "password": "PASSWORD",
}

REDACT_PL: dict[str, str] = {
    "given name": "IMIĘ",
    "surname": "NAZWISKO",
    "person name": "OSOBA",
    "title": "TYTUŁ",
    "gender": "PŁEĆ",
    "sex": "PŁEĆ",
    "age": "WIEK",
    "date": "DATA",
    "email address": "EMAIL",
    "phone number": "TELEFON",
    "social security number": "PESEL",
    "tax number": "NIP",
    "id card number": "DOWÓD",
    "passport number": "PASZPORT",
    "driver licence number": "PRAWO JAZDY",
    "credit card number": "KARTA",
    "street": "ULICA",
    "building number": "NR BUDYNKU",
    "city": "MIASTO",
    "postal code": "KOD POCZTOWY",
    "time": "GODZINA",
    "web address": "URL",
    "pesel": "PESEL",
    "nip": "NIP",
    "regon": "REGON",
    "iban": "IBAN",
    "api key": "KLUCZ API",
    "access token": "TOKEN",
    "private key": "KLUCZ PRYWATNY",
    "password": "HASŁO",
}

RISK_ORDER = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}

ACTION_ORDER = {
    GateAction.ALLOW: 0,
    GateAction.REDACT: 1,
    GateAction.BLOCK: 2,
}


def category_for(label: str) -> SensitivityCategory:
    return LABEL_CATEGORY.get(label, SensitivityCategory.OTHER)


def risk_for(label: str) -> RiskLevel:
    return LABEL_RISK.get(label, RiskLevel.MEDIUM)


def legal_for(label: str) -> str | None:
    return LABEL_LEGAL.get(label)


def redact_token(label: str, locale: str = "en") -> str:
    table = REDACT_PL if locale.lower().startswith("pl") else REDACT_EN
    return table.get(label, COLLAPSE.get(label, label).upper())


def max_risk(levels: list[RiskLevel]) -> RiskLevel:
    if not levels:
        return RiskLevel.NONE
    return max(levels, key=lambda level: RISK_ORDER[level])


def action_for_risk(risk: RiskLevel, *, strict: bool = False) -> GateAction:
    if risk is RiskLevel.CRITICAL:
        return GateAction.BLOCK
    if risk is RiskLevel.HIGH:
        return GateAction.REDACT
    if risk is RiskLevel.MEDIUM:
        return GateAction.REDACT
    if risk is RiskLevel.LOW:
        return GateAction.REDACT if strict else GateAction.ALLOW
    return GateAction.ALLOW
