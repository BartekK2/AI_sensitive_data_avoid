"""Pull prompt text out of AI-vendor JSON and write redactions back."""

from __future__ import annotations

import re
from typing import Any

USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.S)
META_RE = re.compile(
    r"<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_INSTRUCTION)>.*?</\1>",
    re.S,
)
SCAN_PATH_MARKERS = (
    "streamgeneratecontent",
    "generatecontent",
    "chat/completions",
    "/messages",
    "streamcompletions",
)
SKIP_SCAN_MARKERS = (
    "loadcodeassist",
    "listexperiments",
    "fetchuserinfo",
    "fetchavailablemodels",
    "writetrajectory",
    "buildwithgoogleplugins",
    "cascadenuxes",
)
CRITICAL_LABELS = {
    "pesel",
    "nip",
    "regon",
    "api key",
    "access token",
    "private key",
    "password",
    "iban",
    "credit card number",
    "social security number",
    "id card number",
    "passport number",
}

CONTENT_KEYS = {
    "content",
    "text",
    "input",
    "prompt",
    "query",
    "message",
    "user",
    "instruction",
    "system",
    "usermessage",
    "user_message",
    "userinput",
    "prompttext",
    "inputtext",
    "chatmessage",
    "currentusermessage",
    "rawtext",
    "querytext",
    "messagetext",
    "part",
    "parts",
}


def extract_texts(payload: Any) -> list[str]:
    found: list[str] = []
    _walk(payload, found)
    return [item for item in found if item and item.strip()]


def _walk(node: Any, found: list[str], key: str | None = None) -> None:
    if isinstance(node, str):
        if key in CONTENT_KEYS or (key is None and len(node) >= 12):
            found.append(node)
        return
    if isinstance(node, list):
        for item in node:
            _walk(item, found, key)
        return
    if isinstance(node, dict):
        for child_key, value in node.items():
            _walk(value, found, str(child_key).lower().replace("-", ""))


def rewrite_strings(payload: Any, transform) -> Any:
    if isinstance(payload, str):
        return transform(payload)
    if isinstance(payload, list):
        return [rewrite_strings(item, transform) for item in payload]
    if isinstance(payload, dict):
        return {key: rewrite_strings(value, transform) for key, value in payload.items()}
    return payload


def join_texts(texts: list[str]) -> str:
    return "\n\n".join(texts)


def should_scan_destination(destination: str) -> bool:
    dest = (destination or "").lower()
    if any(marker in dest for marker in SKIP_SCAN_MARKERS):
        return False
    if "cloudcode" in dest or "googleapis.com" in dest:
        if any(marker in dest for marker in SCAN_PATH_MARKERS):
            return True
        return "/" not in dest and ":stream" not in dest and ":generate" not in dest
    return True


def is_critical_scan(scan: dict | None) -> bool:
    if not scan:
        return False
    if (scan.get("risk") or "") == "critical":
        for entity in scan.get("entities") or []:
            label = (entity.get("label") or "").lower()
            category = (entity.get("category") or "").lower()
            if label in CRITICAL_LABELS or category in {"government_id", "credentials", "payment_card"}:
                return True
        return False
    for entity in scan.get("entities") or []:
        if (entity.get("label") or "").lower() in CRITICAL_LABELS:
            return True
        if (entity.get("risk") or "") == "critical":
            return True
    return False


def looks_like_vendor_rpc(destination: str) -> bool:
    dest = (destination or "").lower()
    return "cloudcode" in dest or "googleapis.com" in dest or "generativelanguage" in dest


def is_system_boilerplate(text: str) -> bool:
    """Antigravity ships its system prompt as a user turn. That is not the message to gate."""
    sample = (text or "").lstrip()
    head = sample[:120].lower()
    if head.startswith("<identity>") or head.startswith("<system"):
        return True
    if "you are antigravity" in sample[:800].lower():
        return True
    return False


def actor_from_blob(raw: bytes | str) -> dict[str, str | None]:
    """Who sent the prompt, from Antigravity's <user_information>, not from the user text.

    That block has the Windows profile and the repo owner. It does not carry an email.
    """
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else (raw or "")
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\\\", "\\")
    match = re.search(r"<user_information>(.*?)</user_information>", text, re.S | re.I)
    info = match.group(1) if match else ""
    email_match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", info)
    email = email_match.group(0) if email_match else None
    if email and email.split("@", 1)[-1].lower() in {"example.com", "example.org", "test.com"}:
        email = None
    user_match = re.search(r"[A-Za-z]:[\\/]Users[\\/]([^\\/]+)", info, re.I)
    os_user = user_match.group(1) if user_match else None
    corpus = re.search(r"->\s*([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)", info)
    account = corpus.group(1) if corpus else None
    repo = f"{corpus.group(1)}/{corpus.group(2)}" if corpus else None
    if email:
        name = email
    elif os_user and account and os_user.lower() != account.lower():
        name = f"{os_user} ({account})"
    else:
        name = os_user or account
    return {"email": email, "name": name, "team": repo}


def national_id_digits(text: str) -> str | None:
    """9–11 digit identifier in the user message. Skip 10-digit unix timestamps."""
    match = re.search(r"(?<![0-9])(?:\d[ \-]?){9,11}(?![0-9])", text or "")
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) == 10 and not digits.startswith("0"):
        return None
    if len(digits) not in {9, 10, 11}:
        return None
    return digits


def prompt_for_gate(payload: Any, raw: bytes, destination: str = "") -> str:
    blob = raw.decode("utf-8", errors="replace") if raw else ""
    last_turn = last_user_turn_text(payload)
    if last_turn and not is_system_boilerplate(last_turn):
        return isolate_user_request(last_turn)
    tagged = [
        item.strip()
        for item in USER_REQUEST_RE.findall(blob)
        if item.strip() and not is_system_boilerplate(item)
    ]
    if tagged:
        return tagged[-1]
    if payload is not None:
        extracted = join_texts(extract_texts(payload))
        if extracted and len(blob) < 8000:
            return isolate_user_request(extracted)
    if len(blob) < 8000:
        return isolate_user_request(blob)
    return ""


def isolate_user_request(text: str) -> str:
    tagged = USER_REQUEST_RE.findall(text or "")
    if tagged:
        return tagged[-1].strip()
    cleaned = META_RE.sub("", text or "")
    return cleaned.strip()


def last_user_turn_text(payload: Any) -> str:
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        role = str(node.get("role") or node.get("author") or "").lower()
        if role in {"user", "human", "end_user"}:
            text = _plain_turn(node)
            if text:
                found.append(text)
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(payload)
    return found[-1] if found else ""


def _plain_turn(node: dict) -> str:
    chunks: list[str] = []
    parts = node.get("parts")
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
            elif isinstance(part, str):
                chunks.append(part)
    elif isinstance(node.get("text"), str):
        chunks.append(node["text"])
    elif isinstance(node.get("content"), str):
        chunks.append(node["content"])
    return "\n".join(chunk for chunk in chunks if chunk.strip())
