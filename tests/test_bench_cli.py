"""
Unit tests for 'retrylab bench' CLI command and polyglot benchmark reporting.
"""

import json
from pathlib import Path
from typer.testing import CliRunner

from retrylab.benchmark import render_benchmark_table, run_polyglot_benchmark
from retrylab.cli.main import app

runner = CliRunner()


def test_cli_bench_python_table():
    """Verify 'retrylab bench --lang python' generates table report."""
    result = runner.invoke(app, ["bench", "--lang", "python", "--iterations", "10"])
    assert result.exit_code == 0
    assert "RetryLab Polyglot SDK Performance & Latency Benchmark" in result.stdout
    assert "Baseline Transport" in result.stdout
    assert "Zero-Daemon Architecture" in result.stdout


def test_cli_bench_python_json():
    """Verify 'retrylab bench --lang python --format json' outputs valid JSON."""
    result = runner.invoke(app, ["bench", "--lang", "python", "--iterations", "10", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["iterations"] == 10
    assert "python" in data["results"]
    assert "baseline_transport" in data["results"]["python"]["benchmarks"]


def test_cli_bench_invalid_lang():
    """Verify 'retrylab bench --lang invalid' exits with code 1."""
    result = runner.invoke(app, ["bench", "--lang", "unsupported_lang"])
    assert result.exit_code == 1
    assert "Invalid language" in result.stdout


def test_cli_bench_json_out(tmp_path: Path):
    """Verify 'retrylab bench --json-out' writes benchmark data to file."""
    out_file = tmp_path / "bench_report.json"
    result = runner.invoke(app, ["bench", "--lang", "python", "--iterations", "10", "--json-out", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "python" in data["results"]


def test_render_benchmark_table():
    """Verify render_benchmark_table accepts polyglot report."""
    mock_data = {
        "results": {
            "python": {
                "benchmarks": {
                    "baseline_transport": {
                        "mean_us": 35.5,
                        "p50_us": 32.0,
                        "p99_us": 95.0,
                        "throughput_rps": 28169.0,
                        "overhead_us": 0.0,
                    }
                }
            },
            "go": {
                "benchmarks": {
                    "retrylab_passthrough": {
                        "mean_us": 0.65,
                        "p50_us": 0.5,
                        "p99_us": 1.2,
                        "throughput_rps": 1538461.0,
                        "overhead_us": 0.22,
                    }
                }
            },
        }
    }
    table = render_benchmark_table(mock_data)
    assert table is not None
    assert table.row_count == 2
