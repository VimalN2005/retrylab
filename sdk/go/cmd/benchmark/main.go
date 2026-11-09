package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"time"

	"github.com/VimalN2005/retrylab/sdk/go/retrylab"
)

type dummyBaselineRoundTripper struct{}

func (d *dummyBaselineRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	return &http.Response{
		StatusCode: http.StatusOK,
		Header:     make(http.Header),
		Body:       io.NopCloser(bytes.NewBufferString(`{"status":"ok"}`)),
		Request:    req,
	}, nil
}

type Metric struct {
	Iterations    int     `json:"iterations"`
	MeanUS        float64 `json:"mean_us"`
	P50US         float64 `json:"p50_us"`
	P90US         float64 `json:"p90_us"`
	P95US         float64 `json:"p95_us"`
	P99US         float64 `json:"p99_us"`
	MinUS         float64 `json:"min_us"`
	MaxUS         float64 `json:"max_us"`
	ThroughputRPS float64 `json:"throughput_rps"`
	OverheadUS    float64 `json:"overhead_us"`
}

type Report struct {
	Language   string            `json:"language"`
	Timestamp  int64             `json:"timestamp"`
	Iterations int               `json:"iterations"`
	Benchmarks map[string]Metric `json:"benchmarks"`
}

func computePercentiles(durations []float64, baselineMean float64) Metric {
	n := len(durations)
	if n == 0 {
		return Metric{}
	}
	sorted := make([]float64, n)
	copy(sorted, durations)
	sort.Float64s(sorted)

	var total float64
	for _, d := range sorted {
		total += d
	}
	mean := total / float64(n)

	percentile := func(p float64) float64 {
		if n == 1 {
			return sorted[0]
		}
		k := float64(n-1) * (p / 100.0)
		f := math.Floor(k)
		c := math.Ceil(k)
		if f == c {
			return sorted[int(k)]
		}
		return sorted[int(f)]*(c-k) + sorted[int(c)]*(k-f)
	}

	totalSec := total / 1_000_000.0
	rps := 0.0
	if totalSec > 0 {
		rps = float64(n) / totalSec
	}

	overhead := 0.0
	if baselineMean > 0 && mean > baselineMean {
		overhead = mean - baselineMean
	}

	return Metric{
		Iterations:    n,
		MeanUS:        math.Round(mean*100) / 100,
		P50US:         math.Round(percentile(50)*100) / 100,
		P90US:         math.Round(percentile(90)*100) / 100,
		P95US:         math.Round(percentile(95)*100) / 100,
		P99US:         math.Round(percentile(99)*100) / 100,
		MinUS:         math.Round(sorted[0]*100) / 100,
		MaxUS:         math.Round(sorted[n-1]*100) / 100,
		ThroughputRPS: math.Round(rps*10) / 10,
		OverheadUS:    math.Round(overhead*100) / 100,
	}
}

func main() {
	iterFlag := flag.Int("iterations", 1000, "number of iterations")
	jsonFlag := flag.Bool("json", false, "output JSON format")
	flag.Parse()

	iterations := *iterFlag
	warmup := 50

	report := Report{
		Language:   "go",
		Timestamp:  time.Now().Unix(),
		Iterations: iterations,
		Benchmarks: make(map[string]Metric),
	}

	batchSize := 10
	batches := iterations / batchSize
	if batches < 1 {
		batches = 1
		batchSize = iterations
	}

	// 1. Baseline
	clientBase := &http.Client{Transport: &dummyBaselineRoundTripper{}}
	req, _ := http.NewRequest("GET", "https://api.stripe.com/v1/charges", nil)
	for i := 0; i < warmup; i++ {
		resp, _ := clientBase.Do(req)
		_ = resp.Body.Close()
	}
	baseDurations := make([]float64, batches)
	for b := 0; b < batches; b++ {
		t0 := time.Now()
		for i := 0; i < batchSize; i++ {
			resp, _ := clientBase.Do(req)
			_ = resp.Body.Close()
		}
		baseDurations[b] = (float64(time.Since(t0).Nanoseconds()) / 1000.0) / float64(batchSize)
	}
	baseMetric := computePercentiles(baseDurations, 0)
	report.Benchmarks["baseline_transport"] = baseMetric

	// 2. Passthrough
	scenarioPass := retrylab.Scenario{
		Name:       "bench_unmatched",
		URLPattern: "https://api.unmatched.internal/*",
		Fault:      retrylab.FaultTimeout,
	}
	transportPass := retrylab.NewTransport(scenarioPass)
	transportPass.Base = &dummyBaselineRoundTripper{}
	clientPass := &http.Client{Transport: transportPass}
	for i := 0; i < warmup; i++ {
		resp, _ := clientPass.Do(req)
		_ = resp.Body.Close()
	}
	passDurations := make([]float64, batches)
	for b := 0; b < batches; b++ {
		t0 := time.Now()
		for i := 0; i < batchSize; i++ {
			resp, _ := clientPass.Do(req)
			_ = resp.Body.Close()
		}
		passDurations[b] = (float64(time.Since(t0).Nanoseconds()) / 1000.0) / float64(batchSize)
	}
	report.Benchmarks["retrylab_passthrough"] = computePercentiles(passDurations, baseMetric.MeanUS)

	// 3. Fault Injection
	scenarioFault := retrylab.Scenario{
		Name:          "bench_fault_503",
		URLPattern:    "https://api.stripe.com/*",
		Fault:         retrylab.FaultHTTPStatus,
		StatusCode:    http.StatusServiceUnavailable,
		ResponseBody:  `{"error":"service_unavailable"}`,
		FailCount:     99999999,
		RecoverStatus: http.StatusOK,
	}
	transportFault := retrylab.NewTransport(scenarioFault)
	transportFault.Base = &dummyBaselineRoundTripper{}
	clientFault := &http.Client{Transport: transportFault}
	for i := 0; i < warmup; i++ {
		resp, _ := clientFault.Do(req)
		_ = resp.Body.Close()
	}
	faultDurations := make([]float64, batches)
	for b := 0; b < batches; b++ {
		t0 := time.Now()
		for i := 0; i < batchSize; i++ {
			resp, _ := clientFault.Do(req)
			_ = resp.Body.Close()
		}
		faultDurations[b] = (float64(time.Since(t0).Nanoseconds()) / 1000.0) / float64(batchSize)
	}
	report.Benchmarks["retrylab_fault_injection"] = computePercentiles(faultDurations, baseMetric.MeanUS)

	// 4. Idempotency Auditor
	auditor := retrylab.NewIdempotencyAuditor("Idempotency-Key")
	payload := []byte(`{"customer":"cus_999","amount":2000,"currency":"usd"}`)
	hdr := make(http.Header)
	hdr.Set("Idempotency-Key", "tok_bench_123")
	calls := []retrylab.RecordedCall{
		{Method: "POST", URL: "https://api.stripe.com/v1/charges", Headers: hdr, Body: payload, Timestamp: time.Now(), Attempt: 1},
		{Method: "POST", URL: "https://api.stripe.com/v1/charges", Headers: hdr, Body: payload, Timestamp: time.Now(), Attempt: 2},
		{Method: "POST", URL: "https://api.stripe.com/v1/charges", Headers: hdr, Body: payload, Timestamp: time.Now(), Attempt: 3},
	}
	for i := 0; i < warmup; i++ {
		_ = auditor.Audit(calls)
	}
	auditDurations := make([]float64, batches)
	for b := 0; b < batches; b++ {
		t0 := time.Now()
		for i := 0; i < batchSize; i++ {
			_ = auditor.Audit(calls)
		}
		auditDurations[b] = (float64(time.Since(t0).Nanoseconds()) / 1000.0) / float64(batchSize)
	}
	report.Benchmarks["idempotency_auditor"] = computePercentiles(auditDurations, 0)

	if *jsonFlag {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(report)
	} else {
		fmt.Printf("--- RetryLab Go Benchmark (%d iterations) ---\n", iterations)
		for name, b := range report.Benchmarks {
			fmt.Printf("[%s]\n", name)
			fmt.Printf("  Mean: %.2f µs | P50: %.2f µs | P99: %.2f µs\n", b.MeanUS, b.P50US, b.P99US)
			fmt.Printf("  Throughput: %.1f req/s | Overhead: %.2f µs\n", b.ThroughputRPS, b.OverheadUS)
		}
	}
}
