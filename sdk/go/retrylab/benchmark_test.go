package retrylab

import (
	"bytes"
	"io"
	"net/http"
	"testing"
	"time"
)

// dummyBaselineRoundTripper provides a zero-overhead baseline http.RoundTripper.
type dummyBaselineRoundTripper struct{}

func (d *dummyBaselineRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	return &http.Response{
		StatusCode: http.StatusOK,
		Header:     make(http.Header),
		Body:       io.NopCloser(bytes.NewBufferString(`{"status":"ok"}`)),
		Request:    req,
	}, nil
}

func BenchmarkBaselineRoundTripper(b *testing.B) {
	client := &http.Client{Transport: &dummyBaselineRoundTripper{}}
	req, _ := http.NewRequest("GET", "https://api.stripe.com/v1/charges", nil)

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		resp, err := client.Do(req)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		_ = resp.Body.Close()
	}
}

func BenchmarkTransport_Passthrough(b *testing.B) {
	scenario := Scenario{
		Name:       "bench_unmatched",
		URLPattern: "https://api.unmatched.internal/*",
		Fault:      FaultTimeout,
	}
	transport := NewTransport(scenario)
	transport.Base = &dummyBaselineRoundTripper{}
	client := &http.Client{Transport: transport}
	req, _ := http.NewRequest("GET", "https://api.stripe.com/v1/charges", nil)

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		resp, err := client.Do(req)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		_ = resp.Body.Close()
	}
}

func BenchmarkTransport_FaultInjection(b *testing.B) {
	scenario := Scenario{
		Name:          "bench_fault_503",
		URLPattern:    "https://api.stripe.com/*",
		Fault:         FaultHTTPStatus,
		StatusCode:    http.StatusServiceUnavailable,
		ResponseBody:  `{"error":"service_unavailable"}`,
		FailCount:     99999999, // Always inject
		RecoverStatus: http.StatusOK,
		RecoverBody:   `{"status":"recovered"}`,
	}
	transport := NewTransport(scenario)
	transport.Base = &dummyBaselineRoundTripper{}
	client := &http.Client{Transport: transport}
	req, _ := http.NewRequest("POST", "https://api.stripe.com/v1/charges", bytes.NewBufferString(`{"amount":2000}`))

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		resp, err := client.Do(req)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		_ = resp.Body.Close()
	}
}

func BenchmarkIdempotencyAuditor_Audit(b *testing.B) {
	auditor := NewIdempotencyAuditor("Idempotency-Key")
	payload := []byte(`{"customer":"cus_999","amount":2000,"currency":"usd"}`)
	hdr := make(http.Header)
	hdr.Set("Idempotency-Key", "tok_bench_123")

	calls := []RecordedCall{
		{Method: "POST", URL: "https://api.stripe.com/v1/charges", Headers: hdr, Body: payload, Timestamp: time.Now(), Attempt: 1},
		{Method: "POST", URL: "https://api.stripe.com/v1/charges", Headers: hdr, Body: payload, Timestamp: time.Now(), Attempt: 2},
		{Method: "POST", URL: "https://api.stripe.com/v1/charges", Headers: hdr, Body: payload, Timestamp: time.Now(), Attempt: 3},
	}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		report := auditor.Audit(calls)
		if !report.Passed {
			b.Fatalf("expected audit to pass")
		}
	}
}

func BenchmarkBackoffAuditor_Audit(b *testing.B) {
	auditor := NewBackoffAuditor(50*time.Millisecond, 2*time.Second, true)
	now := time.Now()
	calls := []RecordedCall{
		{Attempt: 1, Timestamp: now},
		{Attempt: 2, Timestamp: now.Add(100 * time.Millisecond)},
		{Attempt: 3, Timestamp: now.Add(300 * time.Millisecond)},
	}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		report := auditor.Audit(calls)
		if !report.Passed {
			b.Fatalf("expected backoff audit to pass")
		}
	}
}
