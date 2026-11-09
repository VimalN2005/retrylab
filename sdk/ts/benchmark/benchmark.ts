/**
 * RetryLab TypeScript SDK Benchmark Suite.
 * Measures microsecond latency percentiles (P50, P90, P95, P99), throughput, and memory.
 */

import { performance } from 'node:perf_hooks';
import { createRetryLabFetch } from '../src/fetch-interceptor.ts';
import { IdempotencyAuditor, BackoffAuditor } from '../src/auditor.ts';
import type { Scenario, RecordedCall } from '../src/types.ts';

interface Metric {
  iterations: number;
  mean_us: number;
  p50_us: number;
  p90_us: number;
  p95_us: number;
  p99_us: number;
  min_us: number;
  max_us: number;
  throughput_rps: number;
  overhead_us: number;
}

interface Report {
  language: string;
  timestamp: number;
  iterations: number;
  benchmarks: Record<string, Metric>;
}

function computePercentiles(durationsUs: number[], baselineMeanUs: number = 0): Metric {
  const n = durationsUs.length;
  if (n === 0) {
    return {
      iterations: 0,
      mean_us: 0,
      p50_us: 0,
      p90_us: 0,
      p95_us: 0,
      p99_us: 0,
      min_us: 0,
      max_us: 0,
      throughput_rps: 0,
      overhead_us: 0,
    };
  }

  const sorted = [...durationsUs].sort((a, b) => a - b);
  const totalUs = sorted.reduce((acc, v) => acc + v, 0);
  const mean = totalUs / n;

  function percentile(p: number): number {
    if (n === 1) return sorted[0];
    const k = (n - 1) * (p / 100);
    const f = Math.floor(k);
    const c = Math.ceil(k);
    if (f === c) return sorted[k];
    return sorted[f] * (c - k) + sorted[c] * (k - f);
  }

  const totalSec = totalUs / 1_000_000;
  const throughput = totalSec > 0 ? n / totalSec : 0;
  const overhead = baselineMeanUs > 0 && mean > baselineMeanUs ? mean - baselineMeanUs : 0;

  return {
    iterations: n,
    mean_us: Math.round(mean * 100) / 100,
    p50_us: Math.round(percentile(50) * 100) / 100,
    p90_us: Math.round(percentile(90) * 100) / 100,
    p95_us: Math.round(percentile(95) * 100) / 100,
    p99_us: Math.round(percentile(99) * 100) / 100,
    min_us: Math.round(sorted[0] * 100) / 100,
    max_us: Math.round(sorted[n - 1] * 100) / 100,
    throughput_rps: Math.round(throughput * 10) / 10,
    overhead_us: Math.round(overhead * 100) / 100,
  };
}

async function runBenchmarks() {
  const args = process.argv.slice(2);
  let iterations = 2000;
  let isJson = false;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--iterations' && args[i + 1]) {
      iterations = parseInt(args[i + 1], 10);
      i++;
    } else if (args[i] === '--json') {
      isJson = true;
    }
  }

  const warmup = 50;
  const report: Report = {
    language: 'typescript',
    timestamp: Math.floor(Date.now() / 1000),
    iterations,
    benchmarks: {},
  };

  // Mock baseline fetch
  const mockBaseFetch = async (_input: RequestInfo | URL, _init?: RequestInit) => {
    return new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  // 1. Baseline Fetch
  for (let i = 0; i < warmup; i++) {
    await mockBaseFetch('https://api.stripe.com/v1/charges');
  }
  const baseDurations: number[] = new Array(iterations);
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    await mockBaseFetch('https://api.stripe.com/v1/charges');
    const t1 = performance.now();
    baseDurations[i] = (t1 - t0) * 1000; // ms to us
  }
  const baseMetric = computePercentiles(baseDurations, 0);
  report.benchmarks['baseline_transport'] = baseMetric;

  // 2. RetryLab Passthrough Fetch
  const passthroughScenario: Scenario = {
    name: 'bench_unmatched',
    urlPattern: 'https://api.unmatched.internal/*',
    fault: 'timeout',
  };
  const passFetch = createRetryLabFetch(passthroughScenario, mockBaseFetch as typeof fetch);
  for (let i = 0; i < warmup; i++) {
    await passFetch('https://api.stripe.com/v1/charges');
  }
  const passDurations: number[] = new Array(iterations);
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    await passFetch('https://api.stripe.com/v1/charges');
    const t1 = performance.now();
    passDurations[i] = (t1 - t0) * 1000;
  }
  report.benchmarks['retrylab_passthrough'] = computePercentiles(passDurations, baseMetric.mean_us);

  // 3. RetryLab Fault Injection
  const faultScenario: Scenario = {
    name: 'bench_fault_503',
    urlPattern: 'https://api.stripe.com/*',
    fault: 'http_status',
    statusCode: 503,
    failCount: 99999999,
  };
  const faultFetch = createRetryLabFetch(faultScenario, mockBaseFetch as typeof fetch);
  for (let i = 0; i < warmup; i++) {
    await faultFetch('https://api.stripe.com/v1/charges');
  }
  const faultDurations: number[] = new Array(iterations);
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    await faultFetch('https://api.stripe.com/v1/charges');
    const t1 = performance.now();
    faultDurations[i] = (t1 - t0) * 1000;
  }
  report.benchmarks['retrylab_fault_injection'] = computePercentiles(faultDurations, baseMetric.mean_us);

  // 4. Idempotency Auditor
  const auditor = new IdempotencyAuditor('Idempotency-Key');
  const payloadStr = JSON.stringify({ customer: 'cus_999', amount: 2000, currency: 'usd' });
  const calls: RecordedCall[] = [
    { method: 'POST', url: 'https://api.stripe.com/v1/charges', headers: { 'idempotency-key': 'tok_bench_123' }, body: payloadStr, timestamp: Date.now(), attempt: 1 },
    { method: 'POST', url: 'https://api.stripe.com/v1/charges', headers: { 'idempotency-key': 'tok_bench_123' }, body: payloadStr, timestamp: Date.now(), attempt: 2 },
    { method: 'POST', url: 'https://api.stripe.com/v1/charges', headers: { 'idempotency-key': 'tok_bench_123' }, body: payloadStr, timestamp: Date.now(), attempt: 3 },
  ];
  for (let i = 0; i < warmup; i++) {
    auditor.audit(calls);
  }
  const auditDurations: number[] = new Array(iterations);
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    auditor.audit(calls);
    const t1 = performance.now();
    auditDurations[i] = (t1 - t0) * 1000;
  }
  report.benchmarks['idempotency_auditor'] = computePercentiles(auditDurations, 0);

  // 5. Backoff Auditor
  const backoff = new BackoffAuditor({ minIntervalMs: 50, maxIntervalMs: 2000, enforceBackoff: true });
  const now = Date.now();
  const backoffCalls: RecordedCall[] = [
    { method: 'POST', url: 'https://api.stripe.com/v1/charges', headers: {}, timestamp: now, attempt: 1 },
    { method: 'POST', url: 'https://api.stripe.com/v1/charges', headers: {}, timestamp: now + 100, attempt: 2 },
    { method: 'POST', url: 'https://api.stripe.com/v1/charges', headers: {}, timestamp: now + 300, attempt: 3 },
  ];
  for (let i = 0; i < warmup; i++) {
    backoff.audit(backoffCalls);
  }
  const backoffDurations: number[] = new Array(iterations);
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    backoff.audit(backoffCalls);
    const t1 = performance.now();
    backoffDurations[i] = (t1 - t0) * 1000;
  }
  report.benchmarks['backoff_auditor'] = computePercentiles(backoffDurations, 0);

  if (isJson) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`--- RetryLab TypeScript Benchmark (${iterations} iterations) ---`);
    for (const [name, b] of Object.entries(report.benchmarks)) {
      console.log(`[${name}]`);
      console.log(`  Mean: ${b.mean_us} µs | P50: ${b.p50_us} µs | P99: ${b.p99_us} µs`);
      console.log(`  Throughput: ${b.throughput_rps} req/s | Overhead: ${b.overhead_us} µs`);
    }
  }
}

runBenchmarks().catch(console.error);
