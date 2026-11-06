/**
 * RetryLab TypeScript Resilience Demo.
 * Simulates an AI Agent calling external APIs under intermittent rate limits (HTTP 429)
 * and verifies that exponential backoff and idempotency are correctly preserved.
 */

import { createRetryLabFetch } from '../src/fetch-interceptor.ts';
import { IdempotencyAuditor, BackoffAuditor } from '../src/auditor.ts';

interface CompletionResponse {
  id: string;
  choices: Array<{ message: { content: string } }>;
}

async function callOpenAIWithRetry(
  customFetch: typeof fetch,
  prompt: string,
  idempotencyKey: string,
  maxRetries = 3
): Promise<CompletionResponse> {
  const url = 'https://api.openai.com/v1/chat/completions';
  const body = JSON.stringify({
    model: 'gpt-4o',
    messages: [{ role: 'user', content: prompt }],
  });

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    console.log(`--> [Attempt #${attempt}] POST ${url}`);

    const res = await customFetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body,
    });

    if (res.ok) {
      const data = (await res.json()) as CompletionResponse;
      console.log(`    [SUCCESS] HTTP 200 OK | Response: "${data.choices[0].message.content}"`);
      return data;
    }

    const backoffMs = Math.pow(2, attempt - 1) * 50;
    console.log(`    [TRANSIENT FAILURE] HTTP ${res.status} | Backoff: waiting ${backoffMs}ms...`);
    await new Promise((resolve) => setTimeout(resolve, backoffMs));
  }

  throw new Error(`Failed after ${maxRetries} attempts`);
}

async function runDemo() {
  console.log('================== RETRYLAB TYPESCRIPT SDK RESILIENCE DEMO ==================');

  // 1. Setup in-process chaos: Fail first 2 attempts with HTTP 429, then recover
  const customFetch = createRetryLabFetch({
    name: 'openai-rate-limit-simulation',
    urlPattern: 'api.openai.com',
    method: 'POST',
    fault: 'http_status',
    failCount: 2,
    statusCode: 429,
    responseBody: { error: { message: 'Rate limit exceeded', type: 'requests' } },
    recoverStatus: 200,
    recoverBody: {
      id: 'chatcmpl_live_demo_8829',
      choices: [{ message: { content: 'AI generation recovered successfully!' } }],
    },
  });

  const idempotencyKey = 'idem_ai_prompt_session_99';
  const prompt = 'Synthesize a resilient microservice architecture.';

  const result = await callOpenAIWithRetry(customFetch, prompt, idempotencyKey, 3);

  console.log('\n----------------------------- RELIABILITY AUDIT -----------------------------');
  console.log(`[*] Total Outbound Requests: ${customFetch.attempts}`);
  console.log(`[*] Final Completion ID:    ${result.id}`);

  // 2. Audit idempotency preservation
  const idempotencyAuditor = new IdempotencyAuditor('idempotency-key');
  const idemReport = idempotencyAuditor.audit(customFetch.history);
  console.log(
    `[*] Idempotency Audit:       ${idemReport.passed ? 'PASS' : 'FAIL'} (Key: '${idemReport.keyFound}', Calls: ${idemReport.callsCount})`
  );

  // 3. Audit exponential backoff intervals
  const backoffAuditor = new BackoffAuditor({ minIntervalMs: 20, maxIntervalMs: 1000, enforceBackoff: true });
  const backoffReport = backoffAuditor.audit(customFetch.history);
  console.log(
    `[*] Backoff Timing Audit:    ${backoffReport.passed ? 'PASS' : 'FAIL'} (Delays: [${backoffReport.intervalsMs.map((d) => `${d}ms`).join(', ')}])`
  );
  console.log('=============================================================================');
}

runDemo().catch(console.error);
