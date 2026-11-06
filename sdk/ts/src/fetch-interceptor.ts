/**
 * RetryLab Fetch API Transport Interceptor.
 * Intercepts standard Fetch requests in-process to simulate deterministic API faults and recovery.
 */

import type { Scenario, RecordedCall } from './types.ts';

export interface InterceptedFetch {
  (input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
  readonly attempts: number;
  readonly history: readonly RecordedCall[];
  reset(): void;
}

export function createRetryLabFetch(
  scenario: Scenario,
  baseFetch: typeof fetch = globalThis.fetch
): InterceptedFetch {
  let attemptCounter = 0;
  const recordedHistory: RecordedCall[] = [];

  const failCount = scenario.failCount ?? 1;
  const fault = scenario.fault ?? 'http_status';
  const statusCode = scenario.statusCode ?? 503;
  const recoverStatus = scenario.recoverStatus ?? 200;

  function matches(urlStr: string, methodStr: string): boolean {
    if (scenario.method && scenario.method.toUpperCase() !== methodStr.toUpperCase()) {
      return false;
    }
    if (scenario.urlPattern) {
      if (typeof scenario.urlPattern === 'string') {
        if (!urlStr.includes(scenario.urlPattern)) {
          return false;
        }
      } else if (scenario.urlPattern instanceof RegExp) {
        if (!scenario.urlPattern.test(urlStr)) {
          return false;
        }
      }
    }
    return true;
  }

  const intercepted = async function (
    input: RequestInfo | URL,
    init?: RequestInit
  ): Promise<Response> {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const method = init?.method || (typeof input === 'object' && 'method' in input ? input.method : 'GET');

    if (!matches(url, method)) {
      return baseFetch(input, init);
    }

    attemptCounter++;
    const currentAttempt = attemptCounter;

    // Extract headers
    const headersRecord: Record<string, string> = {};
    if (init?.headers) {
      if (init.headers instanceof Headers) {
        init.headers.forEach((val, key) => {
          headersRecord[key.toLowerCase()] = val;
        });
      } else if (Array.isArray(init.headers)) {
        for (const [k, v] of init.headers) {
          headersRecord[k.toLowerCase()] = v;
        }
      } else {
        for (const [k, v] of Object.entries(init.headers)) {
          headersRecord[k.toLowerCase()] = String(v);
        }
      }
    }

    // Extract body
    let bodyStr = '';
    if (init?.body) {
      if (typeof init.body === 'string') {
        bodyStr = init.body;
      } else if (init.body instanceof Uint8Array) {
        bodyStr = new TextDecoder().decode(init.body);
      }
    }

    recordedHistory.push({
      url,
      method,
      headers: headersRecord,
      body: bodyStr,
      timestamp: Date.now(),
      attempt: currentAttempt,
    });

    // 1. INJECT FAULT
    if (currentAttempt <= failCount) {
      if (scenario.delayMs && scenario.delayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, scenario.delayMs));
      }

      if (fault === 'timeout') {
        throw new DOMException('The operation was aborted due to timeout', 'TimeoutError');
      }

      if (fault === 'network_error') {
        throw new TypeError('fetch failed: connection reset by peer (simulated)');
      }

      if (fault === 'http_status') {
        const bodyContent =
          typeof scenario.responseBody === 'object'
            ? JSON.stringify(scenario.responseBody)
            : scenario.responseBody || '{"error":"Simulated transient failure"}';

        const headers = new Headers({
          'content-type': 'application/json',
          'x-retrylab-fault': 'injected',
        });
        if (statusCode === 429) {
          headers.set('retry-after', '1');
        }

        return new Response(bodyContent, {
          status: statusCode,
          statusText: statusCode === 429 ? 'Too Many Requests' : 'Service Unavailable',
          headers,
        });
      }
    }

    // 2. RECOVER
    const recoverBodyContent =
      typeof scenario.recoverBody === 'object'
        ? JSON.stringify(scenario.recoverBody)
        : scenario.recoverBody || '{"status":"succeeded","service":"retrylab"}';

    return new Response(recoverBodyContent, {
      status: recoverStatus,
      statusText: 'OK',
      headers: new Headers({
        'content-type': 'application/json',
        'x-retrylab-status': 'recovered',
      }),
    });
  };

  Object.defineProperty(intercepted, 'attempts', {
    get: () => attemptCounter,
  });

  Object.defineProperty(intercepted, 'history', {
    get: () => [...recordedHistory],
  });

  (intercepted as any).reset = function () {
    attemptCounter = 0;
    recordedHistory.length = 0;
  };

  return intercepted as InterceptedFetch;
}
