package retrylab

import (
	"net/http"
	"testing"
	"time"
)

func TestIdempotencyAuditorPass(t *testing.T) {
	auditor := NewIdempotencyAuditor()

	headers := make(http.Header)
	headers.Set("Idempotency-Key", "tx_safe_998877")

	calls := []RecordedCall{
		{Headers: headers, Body: []byte(`{"amount": 5000}`), Timestamp: time.Now(), Attempt: 1},
		{Headers: headers, Body: []byte(`{"amount": 5000}`), Timestamp: time.Now().Add(10 * time.Millisecond), Attempt: 2},
	}

	report := auditor.Audit(calls)
	if !report.Passed {
		t.Fatalf("expected audit to pass, got violations: %v", report.Violations)
	}
	if !report.PayloadMatches {
		t.Errorf("expected payload to match")
	}
	if report.KeyFound != "tx_safe_998877" {
		t.Errorf("expected key tx_safe_998877, got %s", report.KeyFound)
	}
}

func TestIdempotencyAuditorKeyMismatch(t *testing.T) {
	auditor := NewIdempotencyAuditor()

	h1 := make(http.Header)
	h1.Set("Idempotency-Key", "key_initial")
	h2 := make(http.Header)
	h2.Set("Idempotency-Key", "key_mutated")

	calls := []RecordedCall{
		{Headers: h1, Body: []byte(`{"order": 1}`), Timestamp: time.Now(), Attempt: 1},
		{Headers: h2, Body: []byte(`{"order": 1}`), Timestamp: time.Now().Add(5 * time.Millisecond), Attempt: 2},
	}

	report := auditor.Audit(calls)
	if report.Passed {
		t.Fatalf("expected audit to fail due to key mismatch")
	}
	if len(report.Violations) == 0 {
		t.Errorf("expected violations to be recorded")
	}
}

func TestIdempotencyAuditorPayloadMutation(t *testing.T) {
	auditor := NewIdempotencyAuditor()

	h := make(http.Header)
	h.Set("Idempotency-Key", "same_key")

	calls := []RecordedCall{
		{Headers: h, Body: []byte(`{"amount": 5000}`), Timestamp: time.Now(), Attempt: 1},
		{Headers: h, Body: []byte(`{"amount": 9999}`), Timestamp: time.Now().Add(5 * time.Millisecond), Attempt: 2},
	}

	report := auditor.Audit(calls)
	if report.Passed {
		t.Fatalf("expected audit to fail due to payload mutation")
	}
	if report.PayloadMatches {
		t.Errorf("expected PayloadMatches to be false")
	}
}

func TestBackoffAuditor(t *testing.T) {
	t0 := time.Now()
	calls := []RecordedCall{
		{Timestamp: t0, Attempt: 1},
		{Timestamp: t0.Add(50 * time.Millisecond), Attempt: 2},
		{Timestamp: t0.Add(150 * time.Millisecond), Attempt: 3}, // delay = 100ms
	}

	auditor := NewBackoffAuditor(20*time.Millisecond, 500*time.Millisecond, true)
	report := auditor.Audit(calls)

	if !report.Passed {
		t.Fatalf("expected backoff audit to pass, got: %v", report.Violations)
	}
	if len(report.Intervals) != 2 {
		t.Errorf("expected 2 intervals, got %d", len(report.Intervals))
	}
}
