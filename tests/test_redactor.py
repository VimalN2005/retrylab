"""
Tests for DataRedactor and safe request sanitization.
"""

import json
from retrylab.models import FaultType, RecordedRequest
from retrylab.security import DataRedactor


def test_redact_sensitive_headers():
    redactor = DataRedactor()
    raw_headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret",
        "X-Api-Key": "live_key_998877",
        "Content-Type": "application/json",
        "User-Agent": "MyApp/1.0",
        "Cookie": "session_id=abcdef123456",
    }
    sanitized = redactor.redact_headers(raw_headers)

    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["X-Api-Key"] == "[REDACTED]"
    assert sanitized["Cookie"] == "[REDACTED]"
    assert sanitized["Content-Type"] == "application/json"
    assert sanitized["User-Agent"] == "MyApp/1.0"


def test_redact_json_body_sensitive_keys():
    redactor = DataRedactor()
    payload = {
        "user": "alice",
        "password": "supersecretpassword123",
        "payment": {
            "card_number": "4111111111111234",
            "cvv": "123",
            "amount": 5000,
        },
        "metadata": {"source": "web"},
    }
    raw_json = json.dumps(payload).encode("utf-8")
    sanitized_str = redactor.redact_body(raw_json)
    sanitized_dict = json.loads(sanitized_str)

    assert sanitized_dict["user"] == "alice"
    assert sanitized_dict["password"] == "[REDACTED]"
    assert sanitized_dict["payment"]["card_number"] == "[REDACTED]"
    assert sanitized_dict["payment"]["cvv"] == "[REDACTED]"
    assert sanitized_dict["payment"]["amount"] == 5000
    assert sanitized_dict["metadata"]["source"] == "web"


def test_redact_raw_openai_key_in_string():
    redactor = DataRedactor()
    text = "Failed while calling OpenAI with key sk-proj1234567890abcdef1234567890xyz"
    sanitized = redactor.redact_body(text)
    assert "sk-[REDACTED]" in sanitized
    assert "sk-proj1234567890abcdef" not in sanitized


def test_recorded_request_to_safe_dict():
    record = RecordedRequest(
        url="https://api.stripe.com/v1/charges",
        method="POST",
        headers={"Authorization": "Bearer rk_live_12345"},
        body=b'{"amount": 1000, "client_secret": "sec_98765"}',
        was_fault_injected=True,
        injected_fault=FaultType.TIMEOUT,
    )
    safe_data = record.to_safe_dict()

    assert safe_data["headers"]["Authorization"] == "[REDACTED]"
    safe_body = json.loads(safe_data["body"])
    assert safe_body["amount"] == 1000
    assert safe_body["client_secret"] == "[REDACTED]"
