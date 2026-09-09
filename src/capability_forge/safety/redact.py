from __future__ import annotations

import re
from typing import Any

# Evidence-only. Replay never reads these files, so redacting them cannot
# change production behavior.

SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
LONG_DIGIT = re.compile(r"\b\d{9,}\b")
BALANCE = re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")

SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "ssn",
    "member_name",
    "full_name",
    "savings_balance",
    "checking_balance",
    "confirmation_id",
}


def redact_text(value: str) -> str:
    value = SSN.sub("[REDACTED_SSN]", value)
    value = EMAIL.sub("[REDACTED_EMAIL]", value)
    value = CC.sub("[REDACTED_PAN]", value)
    value = BALANCE.sub("[REDACTED_AMOUNT]", value)
    value = LONG_DIGIT.sub("[REDACTED_ID]", value)
    return value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            out[key] = "[REDACTED]"
        elif isinstance(value, dict):
            out[key] = redact_mapping(value)
        elif isinstance(value, str):
            out[key] = redact_text(value)
        else:
            out[key] = value
    return out
