"""
Tests for 'retrylab geo' CLI command.
"""

from __future__ import annotations

import json
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_geo_cli_regions_table():
    """Verify 'retrylab geo regions' prints formatted multi-cloud region table."""
    result = runner.invoke(app, ["geo", "regions"])
    assert result.exit_code == 0
    assert "Geographic Regions Registry" in result.stdout
    assert "us-east-1" in result.stdout
    assert "eu-west-1" in result.stdout
    assert "ap-southeast-1" in result.stdout


def test_geo_cli_regions_filter_provider():
    """Verify 'retrylab geo regions --provider GCP' filters only GCP regions."""
    result = runner.invoke(app, ["geo", "regions", "--provider", "GCP"])
    assert result.exit_code == 0
    assert "us-central1" in result.stdout
    assert "europe-west3" in result.stdout
    assert "us-east-1" not in result.stdout


def test_geo_cli_regions_json():
    """Verify 'retrylab geo regions --output json' outputs valid JSON array."""
    result = runner.invoke(app, ["geo", "regions", "--output", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 15
    first = data[0]
    assert "code" in first
    assert "provider" in first
    assert "lat" in first
    assert "lon" in first


def test_geo_cli_matrix_table():
    """Verify 'retrylab geo matrix' renders cross-continental RTT grid."""
    result = runner.invoke(app, ["geo", "matrix"])
    assert result.exit_code == 0
    assert "Global Cloud Cross-Region RTT Matrix" in result.stdout
    assert "us-east-1" in result.stdout
    assert "CLEAN FIBER" in result.stdout


def test_geo_cli_matrix_disruption():
    """Verify 'retrylab geo matrix --disruption undersea_cable_cut' applies chaos banner."""
    result = runner.invoke(app, ["geo", "matrix", "--disruption", "undersea_cable_cut"])
    assert result.exit_code == 0
    assert "CHAOS ACTIVE" in result.stdout
    assert "Transoceanic Fiber Severance" in result.stdout


def test_geo_cli_matrix_json():
    """Verify 'retrylab geo matrix --output json' outputs structured matrix payload."""
    result = runner.invoke(app, ["geo", "matrix", "--hubs-only", "--output", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert "matrix" in data
    assert "region_codes" in data
    assert "us-east-1" in data["matrix"]
    assert data["matrix"]["us-east-1"]["us-east-1"] == 1.5


def test_geo_cli_ping_default():
    """Verify 'retrylab geo ping' runs simulated probe pings between default regions."""
    result = runner.invoke(app, ["geo", "ping", "--count", "5"])
    assert result.exit_code == 0
    assert "Cross-Region Latency Probe" in result.stdout
    assert "us-east-1" in result.stdout
    assert "ap-southeast-1" in result.stdout
    assert "ping statistics" in result.stdout


def test_geo_cli_ping_custom_regions():
    """Verify 'retrylab geo ping --from us-east-1 --to eu-west-1' calculates transatlantic RTT."""
    result = runner.invoke(app, ["geo", "ping", "--from", "us-east-1", "--to", "eu-west-1", "--count", "5"])
    assert result.exit_code == 0
    assert "us-east-1" in result.stdout
    assert "eu-west-1" in result.stdout
    assert "packets transmitted" in result.stdout


def test_geo_cli_ping_disruption_warning():
    """Verify 'retrylab geo ping --disruption solar_storm' shows chaos warning."""
    result = runner.invoke(app, ["geo", "ping", "--disruption", "solar_storm", "--count", "5"])
    assert result.exit_code == 0
    assert "CHAOS WARNING" in result.stdout
    assert "Geomagnetic Solar Activity" in result.stdout


def test_geo_cli_ping_json():
    """Verify 'retrylab geo ping --output json' outputs statistical payload."""
    result = runner.invoke(app, ["geo", "ping", "--from", "us-east-1", "--to", "us-west-2", "--count", "3", "--output", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["source"]["code"] == "us-east-1"
    assert data["destination"]["code"] == "us-west-2"
    assert "distance_km" in data
    assert "baseline_rtt_ms" in data
    assert "samples" in data
    assert len(data["samples"]) == 3


def test_geo_cli_invalid_disruption_exits_nonzero():
    """Verify invalid disruption type returns error code 1."""
    result = runner.invoke(app, ["geo", "ping", "--disruption", "alien_invasion"])
    assert result.exit_code == 1
    assert "Invalid disruption type" in result.stdout


def test_geo_cli_invalid_region_exits_nonzero():
    """Verify unknown region code returns error code 1."""
    result = runner.invoke(app, ["geo", "ping", "--from", "moon-base-alpha", "--to", "us-east-1"])
    assert result.exit_code == 1
    assert "Unknown source region" in result.stdout


def test_geo_cli_invalid_action_exits_nonzero():
    """Verify unknown action returns error code 1."""
    result = runner.invoke(app, ["geo", "teleport"])
    assert result.exit_code == 1
    assert "Unknown action 'teleport'" in result.stdout
