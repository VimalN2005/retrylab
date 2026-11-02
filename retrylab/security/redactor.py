"""
RetryLab Automated Secret & Sensitive Data Redaction Engine.
Prevents leaking API keys, bearer tokens, card numbers, and PII into test logs and CI outputs.
"""

from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "stripe-signature",
    "cookie",
    "set-cookie",
    "x-auth-token",
    "x-amz-security-token",
    "x-hub-signature-256",
}

DEFAULT_SENSITIVE_FIELD_NAMES = {
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "client_secret",
    "card_number",
    "cardnumber",
    "cvv",
    "cvc",
    "ssn",
    "private_key",
}

# Regex patterns for high-risk token values
RE_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE)
RE_OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
RE_CARD_NUMBER = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")


class DataRedactor:
    """
    Sanitizes HTTP headers, query parameters, and JSON payloads.
    """

    def __init__(
        self,
        sensitive_headers: set[str] | None = None,
        sensitive_fields: set[str] | None = None,
        mask: str = "[REDACTED]",
    ) -> None:
        self.sensitive_headers = (
            {h.lower() for h in sensitive_headers}
            if sensitive_headers is not None
            else set(DEFAULT_SENSITIVE_HEADERS)
        )
        self.sensitive_fields = (
            {f.lower() for f in sensitive_fields}
            if sensitive_fields is not None
            else set(DEFAULT_SENSITIVE_FIELD_NAMES)
        )
        self.mask = mask

    def redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Returns a copy of headers with sensitive authorization and cookie tokens masked."""
        sanitized: dict[str, str] = {}
        for k, v in headers.items():
            if k.lower() in self.sensitive_headers:
                sanitized[k] = self.mask
            else:
                # Also check if header value looks like a Bearer token
                val = RE_BEARER.sub(rf"\1{self.mask}", v)
                sanitized[k] = val
        return sanitized

    def _redact_json_value(self, data: Any) -> Any:
        """Recursively walks JSON objects and masks sensitive keys or values."""
        if isinstance(data, dict):
            new_dict: dict[str, Any] = {}
            for k, v in data.items():
                if any(sub in k.lower() for sub in self.sensitive_fields):
                    new_dict[k] = self.mask
                else:
                    new_dict[k] = self._redact_json_value(v)
            return new_dict
        elif isinstance(data, list):
            return [self._redact_json_value(item) for item in data]
        elif isinstance(data, str):
            val = RE_OPENAI_KEY.sub("sk-" + self.mask, data)
            val = RE_CARD_NUMBER.sub("****-****-****-" + self.mask, val)
            return val
        return data

    def redact_body(self, body: bytes | str) -> str:
        """Sanitizes request or response body content."""
        if not body:
            return ""

        raw_str = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)

        # Attempt JSON redaction
        try:
            parsed = json.loads(raw_str)
            sanitized = self._redact_json_value(parsed)
            return json.dumps(sanitized)
        except Exception:
            # Fall back to regex scrubbing on raw text
            text = RE_BEARER.sub(rf"\1{self.mask}", raw_str)
            text = RE_OPENAI_KEY.sub("sk-" + self.mask, text)
            text = RE_CARD_NUMBER.sub("****-****-****-" + self.mask, text)
            return text

    def redact_record(self, record_dict: dict[str, Any]) -> dict[str, Any]:
        """Sanitizes an entire recorded request dict for logging or reporting."""
        sanitized = dict(record_dict)
        if "headers" in sanitized and isinstance(sanitized["headers"], dict):
            sanitized["headers"] = self.redact_headers(sanitized["headers"])
        if "body" in sanitized:
            sanitized["body"] = self.redact_body(sanitized["body"])
        return sanitized
