"""
RetryLab SVG Visual Scorecard Generator.
Generates standalone, responsive vector graphics badges and cards for GitHub PRs and dashboards.
"""

from __future__ import annotations

import html
from retrylab.tui.scorecard import ReliabilityScorecard, ScorecardGrade


def generate_scorecard_svg(scorecard: ReliabilityScorecard, width: int = 740, height: int = 340) -> str:
    """Generate a modern, dark-mode SVG scorecard card representing resilience test outcomes."""
    # Color mapping based on letter grade
    if scorecard.letter_grade in (ScorecardGrade.A_PLUS, ScorecardGrade.A):
        grade_fill = "#10b981"  # Emerald green
        grade_glow = "rgba(16, 185, 129, 0.4)"
        grade_badge_bg = "rgba(16, 185, 129, 0.15)"
    elif scorecard.letter_grade == ScorecardGrade.B:
        grade_fill = "#f59e0b"  # Amber yellow
        grade_glow = "rgba(245, 158, 11, 0.4)"
        grade_badge_bg = "rgba(245, 158, 11, 0.15)"
    else:
        grade_fill = "#ef4444"  # Red
        grade_glow = "rgba(239, 68, 68, 0.4)"
        grade_badge_bg = "rgba(239, 68, 68, 0.15)"

    esc_grade_desc = html.escape(scorecard.grade_description)
    total_endpoints = len(scorecard.endpoints)

    # Generate metric bars
    metrics_svg = []
    y_start = 145
    row_height = 36

    for idx, m in enumerate(scorecard.metrics[:4]):
        y_pos = y_start + (idx * row_height)
        bar_width = 180
        fill_w = max(4, int(round((m.score / 100.0) * bar_width)))
        m_name = html.escape(m.name)
        m_details = html.escape(m.details)

        if m.score >= 90:
            meter_color = "#10b981"
        elif m.score >= 70:
            meter_color = "#06b6d4"
        elif m.score >= 50:
            meter_color = "#f59e0b"
        else:
            meter_color = "#ef4444"

        metrics_svg.append(f"""
    <!-- Metric Row #{idx + 1}: {m_name} -->
    <text x="32" y="{y_pos + 14}" class="metric-label">{m_name}</text>
    <rect x="230" y="{y_pos}" width="{bar_width}" height="14" rx="7" class="bar-bg" />
    <rect x="230" y="{y_pos}" width="{fill_w}" height="14" rx="7" fill="{meter_color}" />
    <text x="424" y="{y_pos + 12}" class="metric-score" fill="{meter_color}">{m.score:.1f}%</text>
    <text x="490" y="{y_pos + 12}" class="metric-details">{m_details}</text>
        """)

    metrics_markup = "\n".join(metrics_svg)

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0b1120" />
      <stop offset="50%" stop-color="#111827" />
      <stop offset="100%" stop-color="#1f2937" />
    </linearGradient>
    <linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#06b6d4" />
      <stop offset="100%" stop-color="#3b82f6" />
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="{grade_glow}" />
    </filter>
  </defs>

  <style>
    .title {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; font-weight: 800; letter-spacing: 1px; fill: #06b6d4; text-transform: uppercase; }}
    .subtitle {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 18px; font-weight: 700; fill: #f8fafc; }}
    .subtext {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 12px; fill: #94a3b8; }}
    .metric-label {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 12px; font-weight: 600; fill: #cbd5e1; }}
    .metric-score {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; font-weight: 700; }}
    .metric-details {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 11px; fill: #94a3b8; }}
    .bar-bg {{ fill: #1e293b; }}
    .footer-text {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 10px; fill: #64748b; }}
    .stat-val {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; font-weight: 700; fill: #38bdf8; }}
    .stat-lbl {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 11px; fill: #94a3b8; }}
  </style>

  <!-- Background Card -->
  <rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="14" fill="url(#bgGrad)" stroke="#334155" stroke-width="1.5" />

  <!-- Top Decorative Accent -->
  <path d="M 2 16 Q 2 2 16 2 L {width - 16} 2 Q {width - 2} 2 {width - 2} 16" fill="none" stroke="url(#headerGrad)" stroke-width="3" />

  <!-- Header Section -->
  <text x="32" y="38" class="title">🧪 RETRYLAB RELIABILITY SCORECARD</text>
  <text x="32" y="66" class="subtitle">API Resilience &amp; Fault Recovery Audit</text>
  <text x="32" y="86" class="subtext">{esc_grade_desc}</text>

  <!-- Grade Badge (Top Right) -->
  <g transform="translate({width - 120}, 28)" filter="url(#glow)">
    <rect x="0" y="0" width="88" height="64" rx="10" fill="{grade_badge_bg}" stroke="{grade_fill}" stroke-width="2" />
    <text x="44" y="38" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Roboto, sans-serif" font-size="28" font-weight="900" fill="{grade_fill}">{scorecard.letter_grade.value}</text>
    <text x="44" y="54" text-anchor="middle" font-family="ui-monospace, monospace" font-size="11" font-weight="700" fill="{grade_fill}">{scorecard.overall_score:.1f}/100</text>
  </g>

  <!-- Divider Line -->
  <line x1="32" y1="108" x2="{width - 32}" y2="108" stroke="#1e293b" stroke-width="1" />

  <!-- Metric Dimension Rows -->
  <g>
{metrics_markup}
  </g>

  <!-- Bottom Divider Line -->
  <line x1="32" y1="290" x2="{width - 32}" y2="290" stroke="#1e293b" stroke-width="1" />

  <!-- Bottom Stats & Footer -->
  <g transform="translate(32, 312)">
    <text x="0" y="4" class="stat-lbl">Audited Calls: <tspan class="stat-val">{scorecard.total_requests}</tspan></text>
    <text x="140" y="4" class="stat-lbl">Injected Chaos: <tspan class="stat-val">{scorecard.total_faults}</tspan></text>
    <text x="290" y="4" class="stat-lbl">Services: <tspan class="stat-val">{total_endpoints}</tspan></text>
    <text x="410" y="4" class="stat-lbl">Recovery Rate: <tspan class="stat-val" fill="#10b981">{scorecard.recovery_rate:.1f}%</tspan></text>
    <text x="{width - 64}" y="4" text-anchor="end" class="footer-text">Powered by RetryLab CI</text>
  </g>
</svg>"""

    return svg_content.strip()
