package retrylab

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

// IdempotencyAuditReport contains results of cryptographic idempotency verification.
type IdempotencyAuditReport struct {
	HeaderName     string
	KeyFound       string
	CallsCount     int
	PayloadMatches bool
	Passed         bool
	Violations     []string
}

// IdempotencyAuditor audits recorded HTTP calls for idempotent retry guarantees.
type IdempotencyAuditor struct {
	HeaderName string
}

// NewIdempotencyAuditor creates an auditor with default header 'Idempotency-Key'.
func NewIdempotencyAuditor(headerName ...string) *IdempotencyAuditor {
	h := "Idempotency-Key"
	if len(headerName) > 0 && headerName[0] != "" {
		h = headerName[0]
	}
	return &IdempotencyAuditor{HeaderName: h}
}

// Audit evaluates recorded requests to verify header preservation and payload stability.
func (a *IdempotencyAuditor) Audit(calls []RecordedCall) *IdempotencyAuditReport {
	report := &IdempotencyAuditReport{
		HeaderName:     a.HeaderName,
		CallsCount:     len(calls),
		PayloadMatches: true,
		Passed:         true,
		Violations:     make([]string, 0),
	}

	if len(calls) <= 1 {
		return report
	}

	var firstKey string
	var firstHash string

	for idx, call := range calls {
		key := call.Headers.Get(a.HeaderName)
		h := sha256.Sum256(call.Body)
		bodyHash := hex.EncodeToString(h[:])

		if idx == 0 {
			firstKey = key
			firstHash = bodyHash
			report.KeyFound = key
			if key == "" {
				report.Violations = append(report.Violations, fmt.Sprintf("call #1 missing '%s' header", a.HeaderName))
				report.Passed = false
			}
			continue
		}

		// Check idempotency header matches initial attempt
		if key != firstKey {
			report.Violations = append(report.Violations,
				fmt.Sprintf("call #%d changed '%s' from '%s' to '%s'", idx+1, a.HeaderName, firstKey, key))
			report.Passed = false
		}

		// Check payload body has not mutated across retries
		if bodyHash != firstHash {
			report.PayloadMatches = false
			report.Violations = append(report.Violations,
				fmt.Sprintf("call #%d mutated payload body (SHA-256 fingerprint mismatch)", idx+1))
			report.Passed = false
		}
	}

	return report
}

// BackoffAuditReport contains results of retry interval and timing verification.
type BackoffAuditReport struct {
	Intervals  []time.Duration
	Passed     bool
	Violations []string
}

// BackoffAuditor verifies exponential progression and budget limits in retry timing.
type BackoffAuditor struct {
	MinInterval time.Duration
	MaxInterval time.Duration
	EnforceBackoff bool
}

// NewBackoffAuditor creates a timing verifier.
func NewBackoffAuditor(minInterval, maxInterval time.Duration, enforceBackoff bool) *BackoffAuditor {
	return &BackoffAuditor{
		MinInterval: minInterval,
		MaxInterval: maxInterval,
		EnforceBackoff: enforceBackoff,
	}
}

// Audit verifies delays between consecutive attempts.
func (b *BackoffAuditor) Audit(calls []RecordedCall) *BackoffAuditReport {
	report := &BackoffAuditReport{
		Intervals:  make([]time.Duration, 0),
		Passed:     true,
		Violations: make([]string, 0),
	}

	if len(calls) <= 1 {
		return report
	}

	var prev time.Time
	for idx, call := range calls {
		if idx == 0 {
			prev = call.Timestamp
			continue
		}

		interval := call.Timestamp.Sub(prev)
		report.Intervals = append(report.Intervals, interval)

		if interval < b.MinInterval {
			report.Violations = append(report.Violations,
				fmt.Sprintf("attempt #%d delay %v is below minimum %v (zero-delay spam detected)",
					idx+1, interval, b.MinInterval))
			report.Passed = false
		}

		if b.MaxInterval > 0 && interval > b.MaxInterval {
			report.Violations = append(report.Violations,
				fmt.Sprintf("attempt #%d delay %v exceeded maximum budget %v",
					idx+1, interval, b.MaxInterval))
			report.Passed = false
		}

		// Check exponential progression if configured
		if b.EnforceBackoff && len(report.Intervals) >= 2 {
			lastIdx := len(report.Intervals) - 1
			currDelay := report.Intervals[lastIdx]
			prevDelay := report.Intervals[lastIdx-1]
			// Current delay should be >= previous delay (allowing small jitter factor 0.8)
			if float64(currDelay) < float64(prevDelay)*0.8 {
				report.Violations = append(report.Violations,
					fmt.Sprintf("attempt #%d delay %v did not backoff from previous delay %v",
						idx+1, currDelay, prevDelay))
				report.Passed = false
			}
		}

		prev = call.Timestamp
	}

	return report
}

// String provides a human-readable summary of the idempotency audit.
func (r *IdempotencyAuditReport) String() string {
	if r.Passed {
		return fmt.Sprintf("PASS (Key: '%s', Calls: %d, Payload Matches: %t)", r.KeyFound, r.CallsCount, r.PayloadMatches)
	}
	return fmt.Sprintf("FAIL (Violations: %s)", strings.Join(r.Violations, "; "))
}
