import test from 'node:test';
import assert from 'node:assert/strict';

import { IdempotencyAuditor, BackoffAuditor } from '../src/auditor.ts';
import type { RecordedCall } from '../src/types.ts';

test('IdempotencyAuditor - Pass with preserved key and matching hash', () => {
  const auditor = new IdempotencyAuditor('idempotency-key');

  const calls: RecordedCall[] = [
    {
      url: 'https://api.stripe.com/v1/charges',
      method: 'POST',
      headers: { 'idempotency-key': 'key_live_12345' },
      body: JSON.stringify({ amount: 1000 }),
      timestamp: 1000,
      attempt: 1,
    },
    {
      url: 'https://api.stripe.com/v1/charges',
      method: 'POST',
      headers: { 'idempotency-key': 'key_live_12345' },
      body: JSON.stringify({ amount: 1000 }),
      timestamp: 1050,
      attempt: 2,
    },
  ];

  const report = auditor.audit(calls);
  assert.equal(report.passed, true);
  assert.equal(report.payloadMatches, true);
  assert.equal(report.keyFound, 'key_live_12345');
  assert.equal(report.violations.length, 0);
});

test('IdempotencyAuditor - Detects mutated payload body', () => {
  const auditor = new IdempotencyAuditor('idempotency-key');

  const calls: RecordedCall[] = [
    {
      url: 'https://api.stripe.com/v1/charges',
      method: 'POST',
      headers: { 'idempotency-key': 'same_key' },
      body: JSON.stringify({ amount: 1000 }),
      timestamp: 1000,
      attempt: 1,
    },
    {
      url: 'https://api.stripe.com/v1/charges',
      method: 'POST',
      headers: { 'idempotency-key': 'same_key' },
      body: JSON.stringify({ amount: 9999 }), // Mutated body
      timestamp: 1050,
      attempt: 2,
    },
  ];

  const report = auditor.audit(calls);
  assert.equal(report.passed, false);
  assert.equal(report.payloadMatches, false);
  assert.ok(report.violations[0].includes('mutated payload body'));
});

test('BackoffAuditor - Verifies exponential delays', () => {
  const calls: RecordedCall[] = [
    { url: '', method: 'GET', headers: {}, body: '', timestamp: 1000, attempt: 1 },
    { url: '', method: 'GET', headers: {}, body: '', timestamp: 1050, attempt: 2 }, // 50ms
    { url: '', method: 'GET', headers: {}, body: '', timestamp: 1150, attempt: 3 }, // 100ms
  ];

  const auditor = new BackoffAuditor({
    minIntervalMs: 20,
    maxIntervalMs: 500,
    enforceBackoff: true,
  });

  const report = auditor.audit(calls);
  assert.equal(report.passed, true);
  assert.deepEqual(report.intervalsMs, [50, 100]);
});
