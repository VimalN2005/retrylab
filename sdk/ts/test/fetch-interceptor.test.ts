import test from 'node:test';
import assert from 'node:assert/strict';

import { createRetryLabFetch } from '../src/fetch-interceptor.ts';

test('Fetch Interceptor - HTTP 429 Injection and Eventual 200 Recovery', async () => {
  const retryFetch = createRetryLabFetch({
    name: 'stripe-rate-limit',
    urlPattern: 'api.stripe.com',
    method: 'POST',
    fault: 'http_status',
    failCount: 2,
    statusCode: 429,
    responseBody: { error: 'rate_limit_exceeded' },
    recoverStatus: 200,
    recoverBody: { id: 'ch_test_123', status: 'succeeded' },
  });

  const url = 'https://api.stripe.com/v1/charges';
  const init = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'key_abc' },
    body: JSON.stringify({ amount: 2000 }),
  };

  // Attempt 1: 429
  const res1 = await retryFetch(url, init);
  assert.equal(res1.status, 429);
  const json1 = await res1.json();
  assert.equal(json1.error, 'rate_limit_exceeded');

  // Attempt 2: 429
  const res2 = await retryFetch(url, init);
  assert.equal(res2.status, 429);

  // Attempt 3: 200
  const res3 = await retryFetch(url, init);
  assert.equal(res3.status, 200);
  const json3 = await res3.json();
  assert.equal(json3.status, 'succeeded');
  assert.equal(json3.id, 'ch_test_123');

  assert.equal(retryFetch.attempts, 3);
  assert.equal(retryFetch.history.length, 3);
  assert.equal(retryFetch.history[0].headers['idempotency-key'], 'key_abc');
});

test('Fetch Interceptor - Timeout Injection', async () => {
  const retryFetch = createRetryLabFetch({
    urlPattern: 'api.timeout.com',
    fault: 'timeout',
    failCount: 1,
    delayMs: 5,
  });

  await assert.rejects(
    async () => {
      await retryFetch('https://api.timeout.com/data');
    },
    (err: any) => {
      return err.name === 'TimeoutError';
    }
  );

  // Attempt 2 recovers
  const res2 = await retryFetch('https://api.timeout.com/data');
  assert.equal(res2.status, 200);
});

test('Fetch Interceptor - Network Error Disconnection', async () => {
  const retryFetch = createRetryLabFetch({
    urlPattern: 'api.disconnect.com',
    fault: 'network_error',
    failCount: 1,
  });

  await assert.rejects(
    async () => {
      await retryFetch('https://api.disconnect.com/stream');
    },
    (err: any) => {
      return err instanceof TypeError && err.message.includes('fetch failed');
    }
  );

  // Attempt 2 recovers
  const res2 = await retryFetch('https://api.disconnect.com/stream');
  assert.equal(res2.status, 200);
});
