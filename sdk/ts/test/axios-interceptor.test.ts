import test from 'node:test';
import assert from 'node:assert/strict';

import { createRetryLabAxiosAdapter } from '../src/axios-interceptor.ts';

test('Axios Adapter - Injects 503 and recovers to 200', async () => {
  const adapter = createRetryLabAxiosAdapter({
    urlPattern: 'api.github.com',
    fault: 'http_status',
    failCount: 1,
    statusCode: 503,
    responseBody: { message: 'Service Unavailable' },
    recoverStatus: 200,
    recoverBody: { login: 'octocat' },
  });

  const config = {
    url: 'https://api.github.com/user',
    method: 'GET',
    headers: { Authorization: 'Bearer token' },
  };

  // Attempt 1: Rejects with 503
  await assert.rejects(
    async () => {
      await adapter(config);
    },
    (err: any) => {
      return err.code === 'ERR_BAD_RESPONSE' && err.response.status === 503;
    }
  );

  // Attempt 2: Resolves with 200 OK
  const res2 = await adapter(config);
  assert.equal(res2.status, 200);
  assert.equal(res2.data.login, 'octocat');

  assert.equal(adapter.attempts, 2);
  assert.equal(adapter.history.length, 2);
});

test('Axios Adapter - Injects timeout error code ECONNABORTED', async () => {
  const adapter = createRetryLabAxiosAdapter({
    urlPattern: 'api.timeout.com',
    fault: 'timeout',
    failCount: 1,
  });

  await assert.rejects(
    async () => {
      await adapter({ url: 'https://api.timeout.com/v1', method: 'POST' });
    },
    (err: any) => {
      return err.code === 'ECONNABORTED';
    }
  );
});
