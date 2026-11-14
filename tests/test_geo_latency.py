"""
Unit tests for RetryLab Multi-Region Latency & Geo-Jitter Chaos Simulator (retrylab.geo).
"""

from __future__ import annotations

import pytest
from rich.table import Table

from retrylab.geo import (
    STANDARD_REGIONS,
    CloudProvider,
    CloudRegion,
    GeoDisruptionType,
    GeoLatencyMatrix,
    GeoSimulationResult,
    calculate_baseline_rtt_ms,
    generate_latency_matrix,
    get_region,
    haversine_distance_km,
    list_regions,
    render_geo_matrix_table,
    render_ping_table,
    render_region_list_table,
    simulate_cross_region_latency,
)


def test_standard_regions_registry_and_lookup():
    """Verify registry contents and case-insensitive region lookup."""
    assert "us-east-1" in STANDARD_REGIONS
    assert "eu-west-1" in STANDARD_REGIONS
    assert "ap-southeast-1" in STANDARD_REGIONS

    reg = get_region("US-EAST-1")
    assert reg is not None
    assert reg.code == "us-east-1"
    assert reg.provider == CloudProvider.AWS
    assert reg.city == "Ashburn, VA"

    # Search by city / name alias
    reg_sg = get_region("Singapore")
    assert reg_sg is not None
    assert "singapore" in reg_sg.code.lower() or "singapore" in reg_sg.city.lower()

    # Unknown region returns None
    assert get_region("mars-olympus-mons-1") is None


def test_list_regions_filtering():
    """Verify list_regions with provider and hub filters."""
    all_regions = list_regions()
    assert len(all_regions) >= 15

    aws_only = list_regions(provider=CloudProvider.AWS)
    assert all(r.provider == CloudProvider.AWS for r in aws_only)
    assert len(aws_only) >= 10

    gcp_only = list_regions(provider=CloudProvider.GCP)
    assert all(r.provider == CloudProvider.GCP for r in gcp_only)
    assert len(gcp_only) >= 3

    hubs = list_regions(hubs_only=True)
    assert all(r.is_hub for r in hubs)
    assert len(hubs) >= 6


def test_haversine_distance_calculation():
    """Verify Earth great-circle distance between coordinates."""
    # Distance from us-east-1 (Ashburn, VA) to eu-west-1 (Dublin, Ireland) ~ 5350 km
    us_east = get_region("us-east-1")
    eu_west = get_region("eu-west-1")
    assert us_east is not None and eu_west is not None

    dist = haversine_distance_km(us_east.lat, us_east.lon, eu_west.lat, eu_west.lon)
    assert 5000 < dist < 6000

    # Distance to self is 0.0 km
    assert haversine_distance_km(us_east.lat, us_east.lon, us_east.lat, us_east.lon) == 0.0


def test_baseline_rtt_calculation():
    """Verify speed-of-light in silica glass fiber RTT calculations."""
    # Intra-datacenter is ~1.5ms
    intra_rtt = calculate_baseline_rtt_ms("us-east-1", "us-east-1")
    assert intra_rtt == 1.5

    # US East to US West ~60-80 ms
    transcon_rtt = calculate_baseline_rtt_ms("us-east-1", "us-west-2")
    assert 50.0 < transcon_rtt < 85.0

    # US East to Europe West (Transatlantic) ~70-95 ms
    transatlantic_rtt = calculate_baseline_rtt_ms("us-east-1", "eu-west-1")
    assert 65.0 < transatlantic_rtt < 100.0

    # US East to Singapore (Transpacific/Eurasian) ~200-260 ms
    intercontinental_rtt = calculate_baseline_rtt_ms("us-east-1", "ap-southeast-1")
    assert 190.0 < intercontinental_rtt < 270.0


def test_simulate_cross_region_clean_probes():
    """Verify deterministic ping simulation without disruption."""
    res = simulate_cross_region_latency(
        src="us-east-1",
        dst="eu-west-1",
        count=15,
        disruption=GeoDisruptionType.NONE,
        seed=42,
    )

    assert isinstance(res, GeoSimulationResult)
    assert res.source.code == "us-east-1"
    assert res.destination.code == "eu-west-1"
    assert res.samples_sent == 15
    assert res.samples_received == 15
    assert res.packet_loss_pct == 0.0
    assert res.min_ms is not None and res.max_ms is not None
    assert res.avg_ms is not None and res.jitter_ms is not None
    assert res.min_ms <= res.avg_ms <= res.max_ms
    assert len(res.samples) == 15
    assert not any(s.dropped for s in res.samples)


def test_simulate_disruption_cable_cut():
    """Verify undersea cable cut injects detour penalty and higher RTT."""
    clean_res = simulate_cross_region_latency(
        src="us-east-1",
        dst="ap-southeast-1",
        count=10,
        disruption=GeoDisruptionType.NONE,
        seed=100,
    )
    cable_cut_res = simulate_cross_region_latency(
        src="us-east-1",
        dst="ap-southeast-1",
        count=10,
        disruption=GeoDisruptionType.UNDERSEA_CABLE_CUT,
        seed=100,
    )

    assert cable_cut_res.disruption == GeoDisruptionType.UNDERSEA_CABLE_CUT
    assert clean_res.avg_ms is not None and cable_cut_res.avg_ms is not None
    # Cable cut should add roughly 80+ ms of rerouting overhead
    assert cable_cut_res.avg_ms > clean_res.avg_ms + 70.0


def test_simulate_disruption_packet_loss_storm():
    """Verify packet loss storm introduces packet drops."""
    res = simulate_cross_region_latency(
        src="us-east-1",
        dst="sa-east-1",
        count=50,
        disruption=GeoDisruptionType.PACKET_LOSS_STORM,
        seed=123,
    )

    assert res.samples_sent == 50
    # In a loss storm with seed 123, some packets must be dropped
    assert any(s.dropped for s in res.samples)
    assert res.packet_loss_pct > 0.0
    assert res.samples_received < 50


def test_satellite_fallback_disruption():
    """Verify GEO satellite fallback introduces ~550ms extra latency."""
    res = simulate_cross_region_latency(
        src="us-east-1",
        dst="us-west-2",
        count=5,
        disruption=GeoDisruptionType.SATELLITE_FALLBACK,
        seed=7,
    )
    assert res.avg_ms is not None
    assert res.avg_ms > 500.0


def test_generate_latency_matrix():
    """Verify N x N cross-region latency matrix generation."""
    hubs = ["us-east-1", "eu-west-1", "ap-southeast-1"]
    matrix = generate_latency_matrix(regions=hubs)

    assert isinstance(matrix, GeoLatencyMatrix)
    assert len(matrix.regions) == 3
    # Check diagonal is intra-region 1.5ms
    for code in hubs:
        assert matrix.matrix[code][code] == 1.5

    # Check non-diagonal values are positive and realistic
    assert matrix.matrix["us-east-1"]["eu-west-1"] > 60.0
    assert matrix.matrix["us-east-1"]["ap-southeast-1"] > 180.0


def test_serialization_to_dict():
    """Verify dictionary serialization for JSON output."""
    res = simulate_cross_region_latency(
        src="us-east-1",
        dst="eu-central-1",
        count=5,
        seed=42,
    )
    d = res.to_dict()
    assert d["source"]["code"] == "us-east-1"
    assert d["destination"]["code"] == "eu-central-1"
    assert d["disruption"] == "none"
    assert "samples" in d
    assert len(d["samples"]) == 5

    matrix = generate_latency_matrix(["us-east-1", "us-west-2"])
    md = matrix.to_dict()
    assert "region_codes" in md
    assert "matrix" in md


def test_rich_table_rendering():
    """Verify Rich table formatting helper functions."""
    res = simulate_cross_region_latency(
        src="us-east-1",
        dst="ap-northeast-1",
        count=5,
        disruption=GeoDisruptionType.UNDERSEA_CABLE_CUT,
        seed=42,
    )
    ping_table = render_ping_table(res)
    assert isinstance(ping_table, Table)
    assert "Cross-Region Latency Probe" in str(ping_table.title)

    matrix = generate_latency_matrix(["us-east-1", "eu-west-1"])
    matrix_table = render_geo_matrix_table(matrix)
    assert isinstance(matrix_table, Table)
    assert "Global Cloud Cross-Region RTT Matrix" in str(matrix_table.title)

    regions_table = render_region_list_table(list_regions()[:5])
    assert isinstance(regions_table, Table)
    assert "Geographic Regions Registry" in str(regions_table.title)


def test_invalid_regions_raise_value_error():
    """Verify invalid source/destination or count raises ValueError."""
    with pytest.raises(ValueError, match="Unknown cloud region"):
        calculate_baseline_rtt_ms("invalid-zone-xyz", "us-east-1")

    with pytest.raises(ValueError, match="Unknown source region"):
        simulate_cross_region_latency("invalid-1", "us-east-1")

    with pytest.raises(ValueError, match="Unknown destination region"):
        simulate_cross_region_latency("us-east-1", "invalid-2")

    with pytest.raises(ValueError, match="Probe count must be >= 1"):
        simulate_cross_region_latency("us-east-1", "eu-west-1", count=0)
