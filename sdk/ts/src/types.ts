/**
 * RetryLab TypeScript SDK Core Types & Definitions.
 */

export type FaultType = 'none' | 'http_status' | 'timeout' | 'network_error';

export interface Scenario {
  name?: string;
  urlPattern?: string | RegExp;
  method?: string;
  fault?: FaultType;
  failCount?: number;
  statusCode?: number;
  responseBody?: any;
  delayMs?: number;
  recoverStatus?: number;
  recoverBody?: any;
}

export interface RecordedCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
  timestamp: number;
  attempt: number;
}
