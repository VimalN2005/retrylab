/**
 * RetryLab Axios Transport Adapter & Interceptor.
 * Enables zero-daemon fault injection and retry testing for Axios HTTP clients.
 */

import type { Scenario, RecordedCall } from './types.ts';

export interface InterceptedAxiosAdapter {
  (config: any): Promise<any>;
  readonly attempts: number;
  readonly history: readonly RecordedCall[];
  reset(): void;
}

export function createRetryLabAxiosAdapter(
  scenario: Scenario,
  baseAdapter?: (config: any) => Promise<any>
): InterceptedAxiosAdapter {
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

  const adapter = async function (config: any): Promise<any> {
    const url = config.url || '';
    const method = (config.method || 'GET').toUpperCase();

    if (!matches(url, method)) {
      if (baseAdapter) {
        return baseAdapter(config);
      }
      throw new Error(`retrylab: unhandled unmatched request in Axios adapter: ${url}`);
    }

    attemptCounter++;
    const currentAttempt = attemptCounter;

    // Normalize headers
    const headersRecord: Record<string, string> = {};
    if (config.headers) {
      for (const [k, v] of Object.entries(config.headers)) {
        if (v !== undefined && v !== null) {
          headersRecord[k.toLowerCase()] = String(v);
        }
      }
    }

    // Normalize body string
    let bodyStr = '';
    if (config.data) {
      bodyStr = typeof config.data === 'string' ? config.data : JSON.stringify(config.data);
    }

    recordedHistory.push({
      url,
      method,
      headers: headersRecord,
      body: bodyStr,
      timestamp: Date.now(),
      attempt: currentAttempt,
    });

    if (scenario.delayMs && scenario.delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, scenario.delayMs));
    }

    // 1. INJECT FAULT
    if (currentAttempt <= failCount) {
      if (fault === 'timeout') {
        const err = new Error(`timeout of ${config.timeout || 0}ms exceeded (Simulated Timeout)`);
        (err as any).code = 'ECONNABORTED';
        (err as any).config = config;
        throw err;
      }

      if (fault === 'network_error') {
        const err = new Error('Network Error (Simulated Connection Reset)');
        (err as any).code = 'ERR_NETWORK';
        (err as any).config = config;
        throw err;
      }

      if (fault === 'http_status') {
        const err = new Error(`Request failed with status code ${statusCode}`);
        (err as any).code = 'ERR_BAD_RESPONSE';
        (err as any).config = config;
        (err as any).response = {
          data: scenario.responseBody || { error: 'Simulated transient failure' },
          status: statusCode,
          statusText: statusCode === 429 ? 'Too Many Requests' : 'Service Unavailable',
          headers: {
            'content-type': 'application/json',
            'x-retrylab-fault': 'injected',
            ...(statusCode === 429 ? { 'retry-after': '1' } : {}),
          },
          config,
        };
        throw err;
      }
    }

    // 2. RECOVER
    return {
      data: scenario.recoverBody || { status: 'succeeded', service: 'retrylab' },
      status: recoverStatus,
      statusText: 'OK',
      headers: {
        'content-type': 'application/json',
        'x-retrylab-status': 'recovered',
      },
      config,
    };
  };

  Object.defineProperty(adapter, 'attempts', {
    get: () => attemptCounter,
  });

  Object.defineProperty(adapter, 'history', {
    get: () => [...recordedHistory],
  });

  (adapter as any).reset = function () {
    attemptCounter = 0;
    recordedHistory.length = 0;
  };

  return adapter as InterceptedAxiosAdapter;
}

export function attachRetryLabToAxios(axiosInstance: any, scenario: Scenario): InterceptedAxiosAdapter {
  const originalAdapter = axiosInstance.defaults?.adapter;
  const adapter = createRetryLabAxiosAdapter(scenario, originalAdapter);
  if (axiosInstance.defaults) {
    axiosInstance.defaults.adapter = adapter;
  }
  return adapter;
}
