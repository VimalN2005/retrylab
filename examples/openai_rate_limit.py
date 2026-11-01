"""
RetryLab Example: Simulating and handling OpenAI HTTP 429 Rate Limits.
"""

import time
import httpx
from retrylab import FaultScenario, FaultType, RetryLabTransport


def call_openai_with_retry(client: httpx.Client, prompt: str, max_retries: int = 3) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}]}

    for attempt in range(1, max_retries + 1):
        response = client.post(url, json=payload)

        if response.status_code == 200:
            print(f"[Attempt {attempt}] Request succeeded! Response: {response.json()}")
            return response.json()

        elif response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "1"))
            print(f"[Attempt {attempt}] Hit 429 Rate Limit! Server requested backoff: {retry_after}s.")
            # In production you would do time.sleep(retry_after)
            continue

        response.raise_for_status()

    raise RuntimeError("Exhausted max retries without success.")


def main():
    print("--- Running RetryLab OpenAI Resilience Simulation ---")
    
    # Configure scenario: First attempt returns 429, second attempt recovers
    scenario = FaultScenario(
        target="https://api.openai.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
        retry_after_seconds=2,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        result = call_openai_with_retry(client, prompt="Hello from RetryLab!")
        print("Final Result:", result)

    print("\nScenario Statistics:")
    print(f"Total requests intercepted: {scenario.total_attempts}")
    for i, req in enumerate(scenario.recorded_requests, 1):
        print(f"  Req #{i}: URL={req.url} | Injected={req.was_fault_injected}")


if __name__ == "__main__":
    main()
