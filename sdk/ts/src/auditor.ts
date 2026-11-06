/**
 * RetryLab TypeScript Idempotency & Backoff Timing Auditor.
 */

import crypto from 'node:crypto';
import type { RecordedCall } from './types.ts';

export interface IdempotencyAuditReport {
  headerName: string;
  keyFound: string | null;
  callsCount: number;
  payloadMatches: boolean;
  passed: boolean;
  violations: string[];
}

export class IdempotencyAuditor {
  readonly headerName: string;

  constructor(headerName: string = 'idempotency-key') {
    this.headerName = headerName.toLowerCase();
  }

  audit(calls: readonly RecordedCall[]): IdempotencyAuditReport {
    const report: IdempotencyAuditReport = {
      headerName: this.headerName,
      keyFound: null,
      callsCount: calls.length,
      payloadMatches: true,
      passed: true,
      violations: [],
    };

    if (calls.length <= 1) {
      return report;
    }

    let firstKey: string | null = null;
    let firstHash: string | null = null;

    for (let i = 0; i < calls.length; i++) {
      const call = calls[i];
      const key = call.headers[this.headerName] || null;
      const hash = crypto.createHash('sha256').update(call.body || '').digest('hex');

      if (i === 0) {
        firstKey = key;
        firstHash = hash;
        report.keyFound = key;
        if (!key) {
          report.violations.push(`call #1 missing '${this.headerName}' header`);
          report.passed = false;
        }
        continue;
      }

      if (key !== firstKey) {
        report.violations.push(
          `call #${i + 1} changed '${this.headerName}' from '${firstKey}' to '${key}'`
        );
        report.passed = false;
      }

      if (hash !== firstHash) {
        report.payloadMatches = false;
        report.violations.push(
          `call #${i + 1} mutated payload body (SHA-256 fingerprint mismatch)`
        );
        report.passed = false;
      }
    }

    return report;
  }
}

export interface BackoffAuditReport {
  intervalsMs: number[];
  passed: boolean;
  violations: string[];
}

export class BackoffAuditor {
  readonly minIntervalMs: number;
  readonly maxIntervalMs?: number;
  readonly enforceBackoff: boolean;

  constructor(options: { minIntervalMs: number; maxIntervalMs?: number; enforceBackoff?: boolean }) {
    this.minIntervalMs = options.minIntervalMs;
    this.maxIntervalMs = options.maxIntervalMs;
    this.enforceBackoff = options.enforceBackoff ?? true;
  }

  audit(calls: readonly RecordedCall[]): BackoffAuditReport {
    const report: BackoffAuditReport = {
      intervalsMs: [],
      passed: true,
      violations: [],
    };

    if (calls.length <= 1) {
      return report;
    }

    let prevTime = calls[0].timestamp;
    for (let i = 1; i < calls.length; i++) {
      const currTime = calls[i].timestamp;
      const interval = currTime - prevTime;
      report.intervalsMs.push(interval);

      if (interval < this.minIntervalMs) {
        report.violations.push(
          `attempt #${i + 1} delay ${interval}ms is below minimum threshold ${this.minIntervalMs}ms (zero-delay spam)`
        );
        report.passed = false;
      }

      if (this.maxIntervalMs && interval > this.maxIntervalMs) {
        report.violations.push(
          `attempt #${i + 1} delay ${interval}ms exceeded maximum budget ${this.maxIntervalMs}ms`
        );
        report.passed = false;
      }

      if (this.enforceBackoff && report.intervalsMs.length >= 2) {
        const lastIdx = report.intervalsMs.length - 1;
        const currDelay = report.intervalsMs[lastIdx];
        const prevDelay = report.intervalsMs[lastIdx - 1];
        if (currDelay < prevDelay * 0.8) {
          report.violations.push(
            `attempt #${i + 1} delay ${currDelay}ms did not back off from previous delay ${prevDelay}ms`
          );
          report.passed = false;
        }
      }

      prevTime = currTime;
    }

    return report;
  }
}
