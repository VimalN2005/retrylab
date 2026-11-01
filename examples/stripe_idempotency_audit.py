"""
RetryLab Fintech Example: Verifying Stripe Payment Retry Idempotency & Duplicate Charge Prevention.
"""

import httpx
from retrylab import (
    FaultScenario,
    FaultType,
    IdempotencyAuditor,
    IdempotencyViolationError,
    RetryLabTransport,
)


def safe_charge_customer(
    client: httpx.Client,
    amount: int,
    idempotency_key: str,
    max_retries: int = 2,
) -> dict:
    """
    Production-grade payment helper:
    Preserves the EXACT same idempotency key across all network retries.
    """
    url = "https://api.stripe.com/v1/charges"
    headers = {"Idempotency-Key": idempotency_key}
    payload = {"amount": amount, "currency": "usd"}

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[Attempt {attempt}] Submitting charge with Key: {idempotency_key}...")
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"[Attempt {attempt}] Charge successful! Transaction confirmed.")
                return response.json()
        except httpx.ReadTimeout:
            print(f"[Attempt {attempt}] Stripe timed out! Preparing safe retry...")
            continue

    raise RuntimeError("Payment processing failed after max retries.")


def main():
    print("--- Running RetryLab Fintech Payment Idempotency Audit ---")

    # Simulate Stripe timing out on attempt 1, then recovering on attempt 2
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = IdempotencyAuditor(idempotency_header="Idempotency-Key")

    with httpx.Client(transport=transport) as client:
        result = safe_charge_customer(
            client=client,
            amount=5000,
            idempotency_key="safe_order_tx_98765",
        )
        print("Payment result:", result)

    # Audit the retry sequence
    print("\nAuditing Idempotency Safety...")
    try:
        auditor.assert_idempotent(scenario)
        print("[PASS] Idempotency safety verified! Zero duplicate payment risk detected.")
    except IdempotencyViolationError as err:
        print("[FAIL] Idempotency violation:", err)


if __name__ == "__main__":
    main()
