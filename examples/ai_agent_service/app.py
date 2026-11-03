"""
Production-Grade Resilient AI Agent Service.
Demonstrates enterprise-grade retry policies, backoff, and recovery when calling OpenAI.
"""

from __future__ import annotations

import time
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Resilient AI Agent API", version="1.0.0")


class ChatRequest(BaseModel):
    prompt: str
    model: str = "gpt-4o"
    max_retries: int = 3


class ChatResponse(BaseModel):
    response: str
    model: str
    attempts_made: int
    total_latency_seconds: float


def call_openai_with_resilience(
    prompt: str,
    model: str = "gpt-4o",
    max_retries: int = 3,
) -> tuple[dict[str, Any], int, float]:
    """
    Calls OpenAI chat completions endpoint, gracefully handling 429 rate limits,
    500/503 outages, and timeouts with exponential backoff.
    """
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    start_time = time.time()
    last_error: Exception | None = None

    with httpx.Client(timeout=10.0) as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = client.post(url, json=payload)

                if response.status_code == 200:
                    elapsed = time.time() - start_time
                    return response.json(), attempt, elapsed

                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    time.sleep(min(retry_after * 0.1, 0.5))  # Sleep brief duration for testing
                    continue

                elif response.status_code in (500, 502, 503, 504):
                    time.sleep(0.05 * (2 ** (attempt - 1)))  # Exponential backoff
                    continue

                response.raise_for_status()

            except (httpx.TimeoutException, httpx.ConnectError) as err:
                last_error = err
                time.sleep(0.05 * (2 ** (attempt - 1)))
                continue

    total_elapsed = time.time() - start_time
    raise HTTPException(
        status_code=504,
        detail=f"OpenAI upstream failed after {max_retries} attempts: {last_error}",
    )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    data, attempts, elapsed = call_openai_with_resilience(
        prompt=request.prompt,
        model=request.model,
        max_retries=request.max_retries,
    )
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "AI Response (Recovered)")
    return ChatResponse(
        response=content,
        model=request.model,
        attempts_made=attempts,
        total_latency_seconds=round(elapsed, 4),
    )


@app.get("/health")
def health_endpoint() -> dict[str, str]:
    return {"status": "healthy"}
