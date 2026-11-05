package retrylab

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestTransportHTTPStatusFailureAndRecovery(t *testing.T) {
	scenario := Scenario{
		Name:          "stripe_rate_limit",
		URLPattern:    "api.stripe.com",
		Method:        "POST",
		Fault:         FaultHTTPStatus,
		FailCount:     2,
		StatusCode:    http.StatusTooManyRequests,
		ResponseBody:  `{"error":"rate_limit_exceeded"}`,
		RecoverStatus: http.StatusOK,
		RecoverBody:   `{"id":"ch_123","status":"succeeded"}`,
	}

	transport := NewTransport(scenario)
	client := &http.Client{Transport: transport}

	// Attempt 1: Injected 429
	req1, _ := http.NewRequest("POST", "https://api.stripe.com/v1/charges", strings.NewReader(`{"amount":100}`))
	resp1, err := client.Do(req1)
	if err != nil {
		t.Fatalf("unexpected error on attempt 1: %v", err)
	}
	defer resp1.Body.Close()
	if resp1.StatusCode != http.StatusTooManyRequests {
		t.Errorf("expected 429, got %d", resp1.StatusCode)
	}

	// Attempt 2: Injected 429
	req2, _ := http.NewRequest("POST", "https://api.stripe.com/v1/charges", strings.NewReader(`{"amount":100}`))
	resp2, err := client.Do(req2)
	if err != nil {
		t.Fatalf("unexpected error on attempt 2: %v", err)
	}
	defer resp2.Body.Close()
	if resp2.StatusCode != http.StatusTooManyRequests {
		t.Errorf("expected 429, got %d", resp2.StatusCode)
	}

	// Attempt 3: Recovers to 200
	req3, _ := http.NewRequest("POST", "https://api.stripe.com/v1/charges", strings.NewReader(`{"amount":100}`))
	resp3, err := client.Do(req3)
	if err != nil {
		t.Fatalf("unexpected error on attempt 3: %v", err)
	}
	defer resp3.Body.Close()
	if resp3.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp3.StatusCode)
	}

	if transport.Attempts() != 3 {
		t.Errorf("expected 3 attempts, got %d", transport.Attempts())
	}
	if len(transport.History()) != 3 {
		t.Errorf("expected 3 history records, got %d", len(transport.History()))
	}
}

func TestTransportTimeout(t *testing.T) {
	scenario := Scenario{
		URLPattern: "api.timeout.com",
		Fault:      FaultTimeout,
		FailCount:  1,
		Delay:      10 * time.Millisecond,
	}

	transport := NewTransport(scenario)
	client := &http.Client{Transport: transport}

	// Attempt 1 -> Timeout error
	req1, _ := http.NewRequest("GET", "https://api.timeout.com/v1/data", nil)
	_, err1 := client.Do(req1)
	if !errors.Is(err1, context.DeadlineExceeded) {
		t.Errorf("expected DeadlineExceeded, got: %v", err1)
	}

	// Attempt 2 -> Recovers to 200
	req2, _ := http.NewRequest("GET", "https://api.timeout.com/v1/data", nil)
	resp2, err2 := client.Do(req2)
	if err2 != nil {
		t.Fatalf("unexpected error on attempt 2: %v", err2)
	}
	defer resp2.Body.Close()
	if resp2.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp2.StatusCode)
	}
}

func TestTransportDisconnect(t *testing.T) {
	scenario := Scenario{
		URLPattern: "api.disconnect.com",
		Fault:      FaultDisconnect,
		FailCount:  1,
	}

	transport := NewTransport(scenario)
	client := &http.Client{Transport: transport}

	// Attempt 1 -> Unexpected EOF
	req1, _ := http.NewRequest("GET", "https://api.disconnect.com/v1/ping", nil)
	_, err1 := client.Do(req1)
	if !errors.Is(err1, io.ErrUnexpectedEOF) {
		t.Errorf("expected ErrUnexpectedEOF, got: %v", err1)
	}

	// Attempt 2 -> 200 OK
	req2, _ := http.NewRequest("GET", "https://api.disconnect.com/v1/ping", nil)
	resp2, err2 := client.Do(req2)
	if err2 != nil {
		t.Fatalf("unexpected error on attempt 2: %v", err2)
	}
	defer resp2.Body.Close()
	if resp2.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp2.StatusCode)
	}
}
