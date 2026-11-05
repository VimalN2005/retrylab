package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"time"

	"github.com/VimalN2005/retrylab/sdk/go/retrylab"
)

type ChargeRequest struct {
	Amount   int64  `json:"amount"`
	Currency string `json:"currency"`
	Customer string `json:"customer"`
}

type ChargeResponse struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}

func executeChargeWithRetry(client *http.Client, reqBody ChargeRequest, idempotencyKey string, maxRetries int) (*ChargeResponse, error) {
	url := "https://api.stripe.com/v1/charges"
	jsonBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}

	for attempt := 1; attempt <= maxRetries; attempt++ {
		req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonBytes))
		if err != nil {
			return nil, err
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Idempotency-Key", idempotencyKey)

		fmt.Printf("--> [Attempt #%d] POST %s\n", attempt, url)
		resp, err := client.Do(req)

		if err == nil && resp.StatusCode == http.StatusOK {
			defer resp.Body.Close()
			var charge ChargeResponse
			if err := json.NewDecoder(resp.Body).Decode(&charge); err != nil {
				return nil, err
			}
			fmt.Printf("    [SUCCESS] Status: 200 OK | Charge ID: %s\n", charge.ID)
			return &charge, nil
		}

		status := 0
		if resp != nil {
			status = resp.StatusCode
			resp.Body.Close()
		}

		// Calculate exponential backoff
		backoff := time.Duration(math.Pow(2, float64(attempt-1))*50) * time.Millisecond
		fmt.Printf("    [TRANSIENT FAILURE] HTTP %d | Retrying after %v...\n", status, backoff)
		time.Sleep(backoff)
	}

	return nil, fmt.Errorf("transaction failed after %d attempts", maxRetries)
}

func main() {
	fmt.Println("====================== RETRYLAB GO SDK RESILIENCE DEMO ======================")

	// 1. Configure in-process failure scenario: Fail first 2 attempts with HTTP 429 Rate Limit
	scenario := retrylab.Scenario{
		Name:          "stripe_rate_limit_demo",
		URLPattern:    "api.stripe.com",
		Method:        "POST",
		Fault:         retrylab.FaultHTTPStatus,
		FailCount:     2,
		StatusCode:    http.StatusTooManyRequests,
		ResponseBody:  `{"error":"rate_limit_exceeded","message":"Too Many Requests"}`,
		RecoverStatus: http.StatusOK,
		RecoverBody:   `{"id":"ch_live_987654321","status":"succeeded"}`,
	}

	transport := retrylab.NewTransport(scenario)
	client := &http.Client{Transport: transport}

	// 2. Execute business transaction
	idempotencyKey := "idem_tx_order_88291"
	req := ChargeRequest{
		Amount:   4999,
		Currency: "usd",
		Customer: "cus_alice_in_wonderland",
	}

	result, err := executeChargeWithRetry(client, req, idempotencyKey, 3)
	if err != nil {
		fmt.Printf("Charge failed: %v\n", err)
		return
	}

	// 3. Audit idempotency and backoff timing
	fmt.Println("\n----------------------------- RELIABILITY AUDIT -----------------------------")
	history := transport.History()
	fmt.Printf("[*] Total Outbound Requests: %d\n", transport.Attempts())
	fmt.Printf("[*] Final Transaction State: %s\n", result.Status)

	auditor := retrylab.NewIdempotencyAuditor("Idempotency-Key")
	report := auditor.Audit(history)
	fmt.Printf("[*] Idempotency Audit:       %s\n", report)

	backoffAuditor := retrylab.NewBackoffAuditor(10*time.Millisecond, 2*time.Second, true)
	backoffReport := backoffAuditor.Audit(history)
	if backoffReport.Passed {
		fmt.Printf("[*] Backoff Timing Audit:    PASS (Intervals: %v)\n", backoffReport.Intervals)
	} else {
		fmt.Printf("[*] Backoff Timing Audit:    FAIL (%v)\n", backoffReport.Violations)
	}
	fmt.Println("=============================================================================")
}
