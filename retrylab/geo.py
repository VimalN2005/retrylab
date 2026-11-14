"""
RetryLab Multi-Region Latency & Geo-Jitter Chaos Simulator (retrylab.geo).

Models cross-cloud, cross-continental network latency, realistic speed-of-light
in glass fiber round-trip times (RTT), and undersea fiber cable disruption chaos.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from rich.box import ROUNDED
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover
    Table = Any  # type: ignore
    ROUNDED = None  # type: ignore
    Text = Any  # type: ignore


class CloudProvider(str, Enum):
    """Supported cloud infrastructure providers."""
    AWS = "AWS"
    GCP = "GCP"
    AZURE = "AZURE"


class GeoDisruptionType(str, Enum):
    """Undersea cable, transit, and cosmic disruption chaos modes."""
    NONE = "none"
    UNDERSEA_CABLE_CUT = "undersea_cable_cut"
    SOLAR_STORM = "solar_storm"
    BGP_ROUTE_HIJACK = "bgp_route_hijack"
    TRANSIT_CONGESTION = "transit_congestion"
    SATELLITE_FALLBACK = "satellite_fallback"
    PACKET_LOSS_STORM = "packet_loss_storm"

    @property
    def display_name(self) -> str:
        names = {
            GeoDisruptionType.NONE: "Clean Fiber Routing",
            GeoDisruptionType.UNDERSEA_CABLE_CUT: "Transoceanic Fiber Severance (Detour Reroute)",
            GeoDisruptionType.SOLAR_STORM: "Geomagnetic Solar Activity (High Jitter & Packet Flap)",
            GeoDisruptionType.BGP_ROUTE_HIJACK: "BGP Route Leak / Suboptimal Peering Detour",
            GeoDisruptionType.TRANSIT_CONGESTION: "Cross-Continental Transit Congestion (Bufferbloat)",
            GeoDisruptionType.SATELLITE_FALLBACK: "GEO Satellite Emergency Link (+550ms Base RTT)",
            GeoDisruptionType.PACKET_LOSS_STORM: "Severe Transoceanic Packet Drop Storm (12% Loss)",
        }
        return names.get(self, self.value)


@dataclass(frozen=True)
class CloudRegion:
    """Geographic cloud provider datacenter region metadata."""
    code: str
    name: str
    provider: CloudProvider
    city: str
    country: str
    lat: float
    lon: float
    is_hub: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "provider": self.provider.value,
            "city": self.city,
            "country": self.country,
            "lat": self.lat,
            "lon": self.lon,
            "is_hub": self.is_hub,
        }


# Canonical registry of multi-cloud regions across the Americas, Europe, Asia-Pacific, Africa, and Middle East
STANDARD_REGIONS: Dict[str, CloudRegion] = {
    # AWS Regions
    "us-east-1": CloudRegion(
        code="us-east-1",
        name="US East (N. Virginia)",
        provider=CloudProvider.AWS,
        city="Ashburn, VA",
        country="USA",
        lat=39.0438,
        lon=-77.4874,
        is_hub=True,
    ),
    "us-west-2": CloudRegion(
        code="us-west-2",
        name="US West (Oregon)",
        provider=CloudProvider.AWS,
        city="Boardman, OR",
        country="USA",
        lat=45.8399,
        lon=-119.7006,
        is_hub=True,
    ),
    "eu-west-1": CloudRegion(
        code="eu-west-1",
        name="Europe (Ireland)",
        provider=CloudProvider.AWS,
        city="Dublin",
        country="Ireland",
        lat=53.3498,
        lon=-6.2603,
        is_hub=True,
    ),
    "eu-central-1": CloudRegion(
        code="eu-central-1",
        name="Europe (Frankfurt)",
        provider=CloudProvider.AWS,
        city="Frankfurt",
        country="Germany",
        lat=50.1109,
        lon=8.6821,
        is_hub=True,
    ),
    "ap-southeast-1": CloudRegion(
        code="ap-southeast-1",
        name="Asia Pacific (Singapore)",
        provider=CloudProvider.AWS,
        city="Singapore",
        country="Singapore",
        lat=1.3521,
        lon=103.8198,
        is_hub=True,
    ),
    "ap-northeast-1": CloudRegion(
        code="ap-northeast-1",
        name="Asia Pacific (Tokyo)",
        provider=CloudProvider.AWS,
        city="Tokyo",
        country="Japan",
        lat=35.6762,
        lon=139.6503,
        is_hub=True,
    ),
    "ap-south-1": CloudRegion(
        code="ap-south-1",
        name="Asia Pacific (Mumbai)",
        provider=CloudProvider.AWS,
        city="Mumbai",
        country="India",
        lat=19.0760,
        lon=72.8777,
        is_hub=True,
    ),
    "sa-east-1": CloudRegion(
        code="sa-east-1",
        name="South America (São Paulo)",
        provider=CloudProvider.AWS,
        city="São Paulo",
        country="Brazil",
        lat=-23.5505,
        lon=-46.6333,
        is_hub=True,
    ),
    "af-south-1": CloudRegion(
        code="af-south-1",
        name="Africa (Cape Town)",
        provider=CloudProvider.AWS,
        city="Cape Town",
        country="South Africa",
        lat=-33.9249,
        lon=18.4241,
        is_hub=False,
    ),
    "me-central-1": CloudRegion(
        code="me-central-1",
        name="Middle East (UAE)",
        provider=CloudProvider.AWS,
        city="Dubai",
        country="UAE",
        lat=25.2048,
        lon=55.2708,
        is_hub=False,
    ),
    "ap-southeast-2": CloudRegion(
        code="ap-southeast-2",
        name="Asia Pacific (Sydney)",
        provider=CloudProvider.AWS,
        city="Sydney",
        country="Australia",
        lat=-33.8688,
        lon=151.2093,
        is_hub=True,
    ),

    # GCP Regions
    "us-central1": CloudRegion(
        code="us-central1",
        name="US Central (Iowa)",
        provider=CloudProvider.GCP,
        city="Council Bluffs, IA",
        country="USA",
        lat=41.2619,
        lon=-95.8608,
        is_hub=True,
    ),
    "europe-west3": CloudRegion(
        code="europe-west3",
        name="Europe West (Frankfurt)",
        provider=CloudProvider.GCP,
        city="Frankfurt",
        country="Germany",
        lat=50.1109,
        lon=8.6821,
        is_hub=False,
    ),
    "asia-east1": CloudRegion(
        code="asia-east1",
        name="Asia East (Taiwan)",
        provider=CloudProvider.GCP,
        city="Changhua County",
        country="Taiwan",
        lat=24.0518,
        lon=120.5161,
        is_hub=False,
    ),

    # Azure Regions
    "eastus": CloudRegion(
        code="eastus",
        name="East US (Virginia)",
        provider=CloudProvider.AZURE,
        city="Boydton, VA",
        country="USA",
        lat=36.6677,
        lon=-78.3875,
        is_hub=False,
    ),
    "westeurope": CloudRegion(
        code="westeurope",
        name="West Europe (Netherlands)",
        provider=CloudProvider.AZURE,
        city="Amsterdam",
        country="Netherlands",
        lat=52.3676,
        lon=4.9041,
        is_hub=False,
    ),
    "southeastasia": CloudRegion(
        code="southeastasia",
        name="Southeast Asia (Singapore)",
        provider=CloudProvider.AZURE,
        city="Singapore",
        country="Singapore",
        lat=1.3521,
        lon=103.8198,
        is_hub=False,
    ),
}


def get_region(identifier: str) -> Optional[CloudRegion]:
    """
    Look up a cloud region by code or partial name (case-insensitive).
    """
    cleaned = identifier.strip().lower()
    if cleaned in STANDARD_REGIONS:
        return STANDARD_REGIONS[cleaned]

    # Search by partial match on code, name, or city
    for r in STANDARD_REGIONS.values():
        if (
            cleaned == r.code.lower()
            or cleaned == r.name.lower()
            or cleaned == r.city.lower()
            or cleaned in r.name.lower()
        ):
            return r
    return None


def list_regions(
    provider: Optional[CloudProvider] = None,
    hubs_only: bool = False,
) -> List[CloudRegion]:
    """
    Return all configured cloud regions, optionally filtered by provider or hub status.
    """
    regions = list(STANDARD_REGIONS.values())
    if provider:
        regions = [r for r in regions if r.provider == provider]
    if hubs_only:
        regions = [r for r in regions if r.is_hub]
    return regions


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth (Haversine formula).
    """
    r = 6371.0  # Earth's radius in kilometers

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)


def calculate_baseline_rtt_ms(
    src: Union[str, CloudRegion],
    dst: Union[str, CloudRegion],
) -> float:
    """
    Calculate baseline physical fiber round-trip time (RTT) in milliseconds.

    Physics model:
    - Speed of light in single-mode silica fiber optic core: c_fiber ~ 200,000 km/s (5 us/km).
    - Round-trip distance = 2 * one-way distance.
    - Terrestrial & submarine cable routing detour factor: 1.35x (cables do not travel as pure great circles).
    - Optical amplifier / transponder / peering router serialization overhead: ~6.0 ms base.
    - Intra-datacenter / local region RTT floor: ~1.5 ms.
    """
    region_a = get_region(src) if isinstance(src, str) else src
    region_b = get_region(dst) if isinstance(dst, str) else dst

    if not region_a or not region_b:
        raise ValueError(f"Unknown cloud region specified: {src!r} or {dst!r}")

    if region_a.code == region_b.code:
        return 1.5

    dist_km = haversine_distance_km(region_a.lat, region_a.lon, region_b.lat, region_b.lon)

    # c_fiber = 200 km/ms; 2 * dist_km * detour / 200
    detour_factor = 1.38
    propagation_rtt = (2.0 * dist_km * detour_factor) / 200.0
    equipment_overhead = 6.5

    baseline = max(2.5, round(propagation_rtt + equipment_overhead, 2))
    return baseline


@dataclass
class GeoLatencySample:
    """Individual probe ping sample with loss and disruption telemetry."""
    sequence: int
    rtt_ms: Optional[float]
    dropped: bool
    disruption: GeoDisruptionType

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "rtt_ms": self.rtt_ms,
            "dropped": self.dropped,
            "disruption": self.disruption.value,
        }


@dataclass
class GeoSimulationResult:
    """Statistical summary of simulated cross-region network latency and disruption."""
    source: CloudRegion
    destination: CloudRegion
    distance_km: float
    baseline_rtt_ms: float
    disruption: GeoDisruptionType
    samples_sent: int
    samples_received: int
    packet_loss_pct: float
    min_ms: Optional[float]
    avg_ms: Optional[float]
    max_ms: Optional[float]
    median_ms: Optional[float]
    p95_ms: Optional[float]
    p99_ms: Optional[float]
    jitter_ms: Optional[float]
    samples: List[GeoLatencySample] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "destination": self.destination.to_dict(),
            "distance_km": self.distance_km,
            "baseline_rtt_ms": self.baseline_rtt_ms,
            "disruption": self.disruption.value,
            "disruption_name": self.disruption.display_name,
            "samples_sent": self.samples_sent,
            "samples_received": self.samples_received,
            "packet_loss_pct": self.packet_loss_pct,
            "min_ms": self.min_ms,
            "avg_ms": self.avg_ms,
            "max_ms": self.max_ms,
            "median_ms": self.median_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "jitter_ms": self.jitter_ms,
            "samples": [s.to_dict() for s in self.samples],
        }


def simulate_cross_region_latency(
    src: Union[str, CloudRegion],
    dst: Union[str, CloudRegion],
    count: int = 10,
    disruption: GeoDisruptionType = GeoDisruptionType.NONE,
    seed: Optional[int] = None,
) -> GeoSimulationResult:
    """
    Simulate cross-region network latency probes with realistic Gaussian jitter,
    tail spikes, packet drops, and chaos disruptions.
    """
    region_a = get_region(src) if isinstance(src, str) else src
    region_b = get_region(dst) if isinstance(dst, str) else dst

    if not region_a:
        raise ValueError(f"Unknown source region: {src}")
    if not region_b:
        raise ValueError(f"Unknown destination region: {dst}")

    if count < 1:
        raise ValueError("Probe count must be >= 1")

    rng = random.Random(seed)
    dist_km = haversine_distance_km(region_a.lat, region_a.lon, region_b.lat, region_b.lon)
    baseline_rtt = calculate_baseline_rtt_ms(region_a, region_b)

    # Disruption modifiers
    extra_latency_base = 0.0
    jitter_stddev = max(0.8, baseline_rtt * 0.04)  # ~4% normal fiber jitter
    loss_probability = 0.0

    if disruption == GeoDisruptionType.UNDERSEA_CABLE_CUT:
        # Cable cut forces rerouting via distant alternative routes
        extra_latency_base = 85.0 + rng.uniform(0.0, 45.0)
        jitter_stddev *= 2.5
        loss_probability = 0.025
    elif disruption == GeoDisruptionType.SOLAR_STORM:
        extra_latency_base = 25.0
        jitter_stddev = max(35.0, baseline_rtt * 0.35)
        loss_probability = 0.06
    elif disruption == GeoDisruptionType.BGP_ROUTE_HIJACK:
        extra_latency_base = 120.0
        jitter_stddev *= 1.8
        loss_probability = 0.015
    elif disruption == GeoDisruptionType.TRANSIT_CONGESTION:
        extra_latency_base = 40.0
        jitter_stddev *= 3.0
        loss_probability = 0.04
    elif disruption == GeoDisruptionType.SATELLITE_FALLBACK:
        extra_latency_base = 540.0
        jitter_stddev = 45.0
        loss_probability = 0.03
    elif disruption == GeoDisruptionType.PACKET_LOSS_STORM:
        extra_latency_base = 10.0
        jitter_stddev *= 1.5
        loss_probability = 0.12

    samples: List[GeoLatencySample] = []
    rtt_values: List[float] = []

    for seq in range(1, count + 1):
        if rng.random() < loss_probability:
            # Packet dropped
            samples.append(
                GeoLatencySample(
                    sequence=seq,
                    rtt_ms=None,
                    dropped=True,
                    disruption=disruption,
                )
            )
        else:
            # Normal distribution with positive skew tail
            normal_jitter = rng.gauss(0.0, jitter_stddev)
            # Occasional tail latency spike (5% chance of p99 tail spike)
            tail_spike = rng.expovariate(1.0 / 25.0) if rng.random() < 0.05 else 0.0

            sample_rtt = baseline_rtt + extra_latency_base + normal_jitter + tail_spike
            # Minimum physical floor
            sample_rtt = max(1.2, round(sample_rtt, 2))
            rtt_values.append(sample_rtt)
            samples.append(
                GeoLatencySample(
                    sequence=seq,
                    rtt_ms=sample_rtt,
                    dropped=False,
                    disruption=disruption,
                )
            )

    received = len(rtt_values)
    loss_pct = round(((count - received) / count) * 100.0, 2)

    if received > 0:
        sorted_rtts = sorted(rtt_values)
        min_rtt = sorted_rtts[0]
        max_rtt = sorted_rtts[-1]
        avg_rtt = round(sum(sorted_rtts) / received, 2)
        med_rtt = round(sorted_rtts[received // 2], 2)
        p95_idx = min(received - 1, int(math.ceil(received * 0.95)) - 1)
        p99_idx = min(received - 1, int(math.ceil(received * 0.99)) - 1)
        p95_rtt = round(sorted_rtts[p95_idx], 2)
        p99_rtt = round(sorted_rtts[p99_idx], 2)

        # Standard deviation (jitter)
        variance = sum((x - avg_rtt) ** 2 for x in sorted_rtts) / received
        jitter = round(math.sqrt(variance), 2)
    else:
        min_rtt = avg_rtt = max_rtt = med_rtt = p95_rtt = p99_rtt = jitter = None

    return GeoSimulationResult(
        source=region_a,
        destination=region_b,
        distance_km=dist_km,
        baseline_rtt_ms=baseline_rtt,
        disruption=disruption,
        samples_sent=count,
        samples_received=received,
        packet_loss_pct=loss_pct,
        min_ms=min_rtt,
        avg_ms=avg_rtt,
        max_ms=max_rtt,
        median_ms=med_rtt,
        p95_ms=p95_rtt,
        p99_ms=p99_rtt,
        jitter_ms=jitter,
        samples=samples,
    )


@dataclass
class GeoLatencyMatrix:
    """Inter-region cross-continental latency matrix across key cloud hubs."""
    regions: List[CloudRegion]
    disruption: GeoDisruptionType
    matrix: Dict[str, Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disruption": self.disruption.value,
            "disruption_name": self.disruption.display_name,
            "region_codes": [r.code for r in self.regions],
            "regions": [r.to_dict() for r in self.regions],
            "matrix": self.matrix,
        }


def generate_latency_matrix(
    regions: Optional[List[Union[str, CloudRegion]]] = None,
    disruption: GeoDisruptionType = GeoDisruptionType.NONE,
) -> GeoLatencyMatrix:
    """
    Generate an N x N cross-region baseline RTT matrix for hub or specified regions.
    """
    selected: List[CloudRegion] = []
    if regions:
        for item in regions:
            reg = get_region(item) if isinstance(item, str) else item
            if reg and reg not in selected:
                selected.append(reg)
    else:
        # Default to primary cross-continental cloud hubs
        hub_codes = [
            "us-east-1",
            "us-west-2",
            "eu-west-1",
            "eu-central-1",
            "ap-southeast-1",
            "ap-northeast-1",
            "ap-south-1",
            "sa-east-1",
        ]
        selected = [STANDARD_REGIONS[c] for c in hub_codes if c in STANDARD_REGIONS]

    matrix_data: Dict[str, Dict[str, float]] = {}

    extra_disruption_ms = 0.0
    if disruption == GeoDisruptionType.UNDERSEA_CABLE_CUT:
        extra_disruption_ms = 95.0
    elif disruption == GeoDisruptionType.SOLAR_STORM:
        extra_disruption_ms = 35.0
    elif disruption == GeoDisruptionType.BGP_ROUTE_HIJACK:
        extra_disruption_ms = 120.0
    elif disruption == GeoDisruptionType.TRANSIT_CONGESTION:
        extra_disruption_ms = 45.0
    elif disruption == GeoDisruptionType.SATELLITE_FALLBACK:
        extra_disruption_ms = 540.0

    for r_src in selected:
        matrix_data[r_src.code] = {}
        for r_dst in selected:
            if r_src.code == r_dst.code:
                matrix_data[r_src.code][r_dst.code] = 1.5
            else:
                base = calculate_baseline_rtt_ms(r_src, r_dst)
                matrix_data[r_src.code][r_dst.code] = round(base + extra_disruption_ms, 2)

    return GeoLatencyMatrix(
        regions=selected,
        disruption=disruption,
        matrix=matrix_data,
    )


# ==============================================================================
# Terminal Visualization Helpers
# ==============================================================================

def render_ping_table(result: GeoSimulationResult) -> Table:
    """
    Render an informative Rich Table summarizing simulated cross-region ping probes.
    """
    table = Table(
        title=f"🌐 Cross-Region Latency Probe: [bold cyan]{result.source.code}[/] ➔ [bold cyan]{result.destination.code}[/]",
        box=ROUNDED,
        header_style="bold magenta",
    )

    table.add_column("Seq", justify="center", style="dim", width=5)
    table.add_column("RTT (ms)", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Simulated Path Telemetry", justify="left")

    for sample in result.samples:
        if sample.dropped:
            rtt_str = "[bold red]DROPPED[/]"
            status_str = "❌ [red]LOSS[/]"
            info = f"[red]Packet dropped ({sample.disruption.display_name})[/]"
        else:
            rtt_val = sample.rtt_ms or 0.0
            color = "green" if rtt_val < 80 else ("yellow" if rtt_val < 180 else "red")
            rtt_str = f"[{color}]{rtt_val:.2f} ms[/]"
            status_str = "✅ [green]RECV[/]"
            delta = rtt_val - result.baseline_rtt_ms
            info = f"Δ {delta:+.2f} ms vs baseline ({result.baseline_rtt_ms:.1f} ms)"

        table.add_row(str(sample.sequence), rtt_str, status_str, info)

    return table


def render_geo_matrix_table(matrix: GeoLatencyMatrix) -> Table:
    """
    Render an N x N cross-region RTT matrix as a Rich Table.
    """
    title = f"🌐 Global Cloud Cross-Region RTT Matrix ({matrix.disruption.display_name})"
    table = Table(title=title, box=ROUNDED, header_style="bold cyan")

    table.add_column("Source / Target", justify="left", style="bold white", width=16)

    for reg in matrix.regions:
        table.add_column(reg.code, justify="right", style="cyan")

    for r_src in matrix.regions:
        row: List[str] = [f"[bold]{r_src.code}[/]"]
        for r_dst in matrix.regions:
            val = matrix.matrix[r_src.code][r_dst.code]
            if r_src.code == r_dst.code:
                row.append(f"[dim]{val:.1f}[/]")
            elif val < 80:
                row.append(f"[green]{val:.1f}[/]")
            elif val < 180:
                row.append(f"[yellow]{val:.1f}[/]")
            else:
                row.append(f"[red]{val:.1f}[/]")
        table.add_row(*row)

    return table


def render_region_list_table(regions: List[CloudRegion]) -> Table:
    """
    Render a clean listing of available cloud regions.
    """
    table = Table(
        title="🌍 RetryLab Multi-Cloud Geographic Regions Registry",
        box=ROUNDED,
        header_style="bold blue",
    )
    table.add_column("Region Code", style="bold cyan", no_wrap=True)
    table.add_column("Cloud Provider", justify="center")
    table.add_column("Name")
    table.add_column("Location")
    table.add_column("Coordinates", justify="right")
    table.add_column("Hub", justify="center")

    for r in regions:
        hub_str = "⭐" if r.is_hub else "—"
        coords = f"{r.lat:.2f}°, {r.lon:.2f}°"
        loc = f"{r.city}, {r.country}"
        provider_color = (
            "orange3" if r.provider == CloudProvider.AWS
            else ("blue" if r.provider == CloudProvider.GCP else "deep_sky_blue1")
        )
        provider_str = f"[{provider_color}]{r.provider.value}[/]"
        table.add_row(r.code, provider_str, r.name, loc, coords, hub_str)

    return table
