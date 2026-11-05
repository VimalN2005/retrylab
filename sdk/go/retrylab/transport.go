package retrylab

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// FaultType defines simulated transport failures.
type FaultType string

const (
	FaultNone       FaultType = "none"
	FaultHTTPStatus FaultType = "http_status"
	FaultTimeout    FaultType = "timeout"
	FaultDisconnect FaultType = "disconnect"
)

// Scenario defines request matching criteria and injected chaos parameters.
type Scenario struct {
	Name          string        `json:"name" yaml:"name"`
	URLPattern    string        `json:"url_pattern" yaml:"url_pattern"`
	Method        string        `json:"method" yaml:"method"`
	Fault         FaultType     `json:"fault" yaml:"fault"`
	FailCount     int           `json:"fail_count" yaml:"fail_count"`
	StatusCode    int           `json:"status_code" yaml:"status_code"`
	ResponseBody  string        `json:"response_body" yaml:"response_body"`
	Delay         time.Duration `json:"delay" yaml:"delay"`
	RecoverStatus int           `json:"recover_status" yaml:"recover_status"`
	RecoverBody   string        `json:"recover_body" yaml:"recover_body"`
}

// RecordedCall stores metadata of an intercepted HTTP request.
type RecordedCall struct {
	Method    string
	URL       string
	Headers   http.Header
	Body      []byte
	Timestamp time.Time
	Attempt   int
}

// Transport implements http.RoundTripper for deterministic fault injection.
type Transport struct {
	Base     http.RoundTripper
	Scenario Scenario

	mu       sync.Mutex
	attempts int
	history  []RecordedCall
}

// NewTransport creates an in-process fault intercepting RoundTripper.
func NewTransport(scenario Scenario) *Transport {
	if scenario.RecoverStatus == 0 {
		scenario.RecoverStatus = http.StatusOK
	}
	if scenario.StatusCode == 0 {
		scenario.StatusCode = http.StatusServiceUnavailable
	}
	if scenario.RecoverBody == "" {
		scenario.RecoverBody = `{"status":"recovered","service":"retrylab"}`
	}
	return &Transport{
		Base:     http.DefaultTransport,
		Scenario: scenario,
		history:  make([]RecordedCall, 0),
	}
}

// Attempts returns the number of requests intercepted by this transport.
func (t *Transport) Attempts() int {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.attempts
}

// History returns a copy of all intercepted requests.
func (t *Transport) History() []RecordedCall {
	t.mu.Lock()
	defer t.mu.Unlock()
	copied := make([]RecordedCall, len(t.history))
	copy(copied, t.history)
	return copied
}

// Reset clears recorded attempts and history.
func (t *Transport) Reset() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.attempts = 0
	t.history = make([]RecordedCall, 0)
}

// Matches checks if the request matches the scenario's URL pattern and method.
func (t *Transport) Matches(req *http.Request) bool {
	if t.Scenario.Method != "" && !strings.EqualFold(req.Method, t.Scenario.Method) {
		return false
	}
	if t.Scenario.URLPattern != "" && !strings.Contains(req.URL.String(), t.Scenario.URLPattern) {
		return false
	}
	return true
}

// RoundTrip executes request interception, failure simulation, or recovery.
func (t *Transport) RoundTrip(req *http.Request) (*http.Response, error) {
	if !t.Matches(req) {
		if t.Base != nil {
			return t.Base.RoundTrip(req)
		}
		return nil, fmt.Errorf("retrylab: request unmatched and no base transport configured")
	}

	t.mu.Lock()
	t.attempts++
	attempt := t.attempts

	// Read and buffer request body for auditing
	var bodyBytes []byte
	if req.Body != nil {
		var err error
		bodyBytes, err = io.ReadAll(req.Body)
		if err == nil {
			req.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
		}
	}

	t.history = append(t.history, RecordedCall{
		Method:    req.Method,
		URL:       req.URL.String(),
		Headers:   req.Header.Clone(),
		Body:      bodyBytes,
		Timestamp: time.Now(),
		Attempt:   attempt,
	})
	t.mu.Unlock()

	// 1. INJECT FAULT (while attempt <= FailCount)
	if attempt <= t.Scenario.FailCount {
		switch t.Scenario.Fault {
		case FaultTimeout:
			if t.Scenario.Delay > 0 {
				time.Sleep(t.Scenario.Delay)
			}
			return nil, context.DeadlineExceeded

		case FaultDisconnect:
			return nil, io.ErrUnexpectedEOF

		case FaultHTTPStatus:
			if t.Scenario.Delay > 0 {
				time.Sleep(t.Scenario.Delay)
			}
			resp := &http.Response{
				StatusCode: t.Scenario.StatusCode,
				Status:     fmt.Sprintf("%d %s", t.Scenario.StatusCode, http.StatusText(t.Scenario.StatusCode)),
				Proto:      "HTTP/1.1",
				ProtoMajor: 1,
				ProtoMinor: 1,
				Header:     make(http.Header),
				Body:       io.NopCloser(strings.NewReader(t.Scenario.ResponseBody)),
				Request:    req,
			}
			resp.Header.Set("Content-Type", "application/json")
			resp.Header.Set("X-RetryLab-Fault", "injected")
			if t.Scenario.StatusCode == http.StatusTooManyRequests {
				resp.Header.Set("Retry-After", "1")
			}
			return resp, nil
		}
	}

	// 2. RECOVER (clean recovery response)
	resp := &http.Response{
		StatusCode: t.Scenario.RecoverStatus,
		Status:     fmt.Sprintf("%d %s", t.Scenario.RecoverStatus, http.StatusText(t.Scenario.RecoverStatus)),
		Proto:      "HTTP/1.1",
		ProtoMajor: 1,
		ProtoMinor: 1,
		Header:     make(http.Header),
		Body:       io.NopCloser(strings.NewReader(t.Scenario.RecoverBody)),
		Request:    req,
	}
	resp.Header.Set("Content-Type", "application/json")
	resp.Header.Set("X-RetryLab-Status", "recovered")
	return resp, nil
}
