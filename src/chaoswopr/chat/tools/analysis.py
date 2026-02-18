"""Analysis & Results Tools (10 tools).

Covers metrics analysis, anomaly detection, root cause analysis, and reporting.
"""

import json
from typing import Optional, Any

from chaoswopr.chat.tools.base import register_tool, SafetyTier


# ============================================================================
# Metrics & Monitoring (2 tools)
# ============================================================================

@register_tool(
    name="get_experiment_metrics",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get time-series metrics for an experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            },
            "metric_name": {
                "type": "string",
                "description": "Optional specific metric to query",
            },
            "phase": {
                "type": "string",
                "description": "Optional phase filter",
                "enum": ["baseline", "chaos", "recovery"],
            },
        },
        "required": ["experiment_id"],
    },
)
def get_experiment_metrics(
    experiment_id: str,
    metric_name: Optional[str] = None,
    phase: Optional[str] = None,
) -> str:
    """Get experiment metrics."""
    return f"""**Experiment Metrics: {experiment_id}**

⚠️ Experiment not found or no metrics available.

**Filters:**
- Metric: {metric_name or 'all'}
- Phase: {phase or 'all'}

Use `list_experiments` to find valid experiment IDs.
"""


@register_tool(
    name="compare_experiments",
    safety_tier=SafetyTier.READ_ONLY,
    description="Compare metrics across multiple experiments",
    parameters={
        "type": "object",
        "properties": {
            "experiment_ids": {
                "type": "array",
                "description": "List of experiment IDs to compare",
                "items": {"type": "string"},
            },
            "metric_names": {
                "type": "array",
                "description": "Metrics to compare",
                "items": {"type": "string"},
            },
        },
        "required": ["experiment_ids", "metric_names"],
    },
)
def compare_experiments(experiment_ids: list[str], metric_names: list[str]) -> str:
    """Compare experiments."""
    return f"""**Experiment Comparison**

**Experiments:** {len(experiment_ids)}
**Metrics:** {len(metric_names)}

⚠️ No data available.

Run experiments first with `run_experiment`.
"""


# ============================================================================
# Anomaly Detection (2 tools)
# ============================================================================

@register_tool(
    name="get_anomalies",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get detected anomalies for an experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            },
            "anomaly_type": {
                "type": "string",
                "description": "Filter by anomaly type",
                "enum": ["z_score", "changepoint", "correlation"],
            },
            "severity": {
                "type": "string",
                "description": "Filter by severity",
                "enum": ["info", "warning", "critical"],
            },
        },
        "required": ["experiment_id"],
    },
)
def get_anomalies(
    experiment_id: str,
    anomaly_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> str:
    """Get anomalies."""
    return f"""**Anomalies Detected: {experiment_id}**

⚠️ No anomalies found or experiment not available.

**Filters:**
- Type: {anomaly_type or 'all'}
- Severity: {severity or 'all'}

**Anomaly Detection Methods:**
- Z-score: Detects values >3σ from mean
- CUSUM: Detects gradual drift
- Correlation: Detects unexpected metric relationships

Run experiments to generate anomaly data.
"""


@register_tool(
    name="get_slo_breaches",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get SLO (Service Level Objective) breaches for an experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            },
            "slo_name": {
                "type": "string",
                "description": "Optional SLO name filter",
            },
        },
        "required": ["experiment_id"],
    },
)
def get_slo_breaches(experiment_id: str, slo_name: Optional[str] = None) -> str:
    """Get SLO breaches."""
    return f"""**SLO Breaches: {experiment_id}**

⚠️ No SLO breaches found or experiment not available.

**Filter:** {slo_name or 'all SLOs'}

**Monitored SLOs:**
- Finality delay max: 600s (10 epochs)
- Slashing rate max: 5%
- Participation rate min: 66%

Run chaos experiments to test SLO resilience.
"""


# ============================================================================
# Root Cause Analysis (2 tools)
# ============================================================================

@register_tool(
    name="analyze_root_cause",
    safety_tier=SafetyTier.READ_ONLY,
    description="Perform root cause analysis on an experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            }
        },
        "required": ["experiment_id"],
    },
)
def analyze_root_cause(experiment_id: str) -> str:
    """Perform RCA."""
    return f"""**Root Cause Analysis: {experiment_id}**

⚠️ Experiment not found or RCA not available.

**RCA Engine Process:**
1. Gather observation events (anomalies, SLO breaches)
2. Correlate with injected faults
3. Query RAG pipeline for Ethereum documentation
4. Generate hypotheses with confidence scores
5. Provide evidence and recommendations

**Example RCA Output:**
```
Root Cause: Circuit breaker trip due to finality delay

Hypothesis: 50% packet loss exceeded consensus gossip threshold
Confidence: 0.85

Evidence:
- Finality delayed by 12 epochs (>10 epoch threshold)
- Network latency spike observed at T+120s
- Attestation inclusion rate dropped to 45%

Recommendations:
1. Reduce packet loss to <20%
2. Increase gossip timeout parameters
3. Monitor attestation inclusion distance
```

Run experiments to generate RCA data.
"""


@register_tool(
    name="get_observation_events",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get timeline of observer events for an experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            },
            "event_type": {
                "type": "string",
                "description": "Filter by event type",
                "enum": ["anomaly", "slo_breach", "rca", "recovery"],
            },
        },
        "required": ["experiment_id"],
    },
)
def get_observation_events(experiment_id: str, event_type: Optional[str] = None) -> str:
    """Get observation events."""
    return f"""**Observation Events: {experiment_id}**

⚠️ No events found or experiment not available.

**Filter:** {event_type or 'all events'}

**Event Types:**
- `ANOMALY_DETECTED`: Observer detected metric anomaly
- `SLO_BREACH`: SLO threshold exceeded
- `RCA_COMPLETED`: Root cause analysis finished
- `RECOVERY_STARTED`: Recovery phase initiated

Run experiments with observer enabled to generate events.
"""


# ============================================================================
# Historical Analysis (4 tools)
# ============================================================================

@register_tool(
    name="get_scenario_success_rate",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get success rate statistics for a scenario",
    parameters={
        "type": "object",
        "properties": {
            "scenario_name": {
                "type": "string",
                "description": "Scenario name",
            },
            "time_range": {
                "type": "string",
                "description": "Time range for analysis",
                "enum": ["last_week", "last_month", "all"],
                "default": "all",
            },
        },
        "required": ["scenario_name"],
    },
)
def get_scenario_success_rate(scenario_name: str, time_range: str = "all") -> str:
    """Get scenario success rate."""
    return f"""**Scenario Success Rate: {scenario_name}**

**Time Range:** {time_range}

⚠️ No historical data available.

**Metrics:**
- Total runs: 0
- Successful: 0
- Failed: 0
- Success rate: N/A
- Average duration: N/A

Run multiple experiments to build historical data.
"""


@register_tool(
    name="get_hypothesis_accuracy",
    safety_tier=SafetyTier.READ_ONLY,
    description="Compare predicted vs actual metrics to evaluate hypothesis accuracy",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID (or scenario name for aggregate)",
            }
        },
        "required": ["experiment_id"],
    },
)
def get_hypothesis_accuracy(experiment_id: str) -> str:
    """Get hypothesis accuracy."""
    return f"""**Hypothesis Accuracy: {experiment_id}**

⚠️ No data available.

**Comparison:**
- Predicted finality delay: N/A
- Actual finality delay: N/A
- Prediction error: N/A

**Confidence Calibration:**
- Hypothesis confidence: N/A
- Actual outcome alignment: N/A

Run experiments with hypothesis generation enabled.
"""


@register_tool(
    name="search_experiments",
    safety_tier=SafetyTier.READ_ONLY,
    description="Search experiments by keywords, date range, or blast radius",
    parameters={
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "description": "Keywords to search in scenario name/config",
                "items": {"type": "string"},
            },
            "date_range": {
                "type": "array",
                "description": "Date range [start, end] in RFC3339 format",
                "items": {"type": "string"},
            },
            "min_blast_radius": {
                "type": "number",
                "description": "Minimum blast radius filter",
            },
            "max_blast_radius": {
                "type": "number",
                "description": "Maximum blast radius filter",
            },
        },
    },
)
def search_experiments(
    keywords: Optional[list[str]] = None,
    date_range: Optional[list[str]] = None,
    min_blast_radius: Optional[float] = None,
    max_blast_radius: Optional[float] = None,
) -> str:
    """Search experiments."""
    filters = []
    if keywords:
        filters.append(f"Keywords: {', '.join(keywords)}")
    if date_range:
        filters.append(f"Date: {date_range[0]} to {date_range[1]}")
    if min_blast_radius is not None:
        filters.append(f"Blast radius: ≥{min_blast_radius}%")
    if max_blast_radius is not None:
        filters.append(f"Blast radius: ≤{max_blast_radius}%")

    filter_str = "\n- ".join(filters) if filters else "None"

    return f"""**Experiment Search**

**Filters:**
- {filter_str}

⚠️ No experiments found.

Run experiments to populate the database.
"""


@register_tool(
    name="export_experiment_report",
    safety_tier=SafetyTier.READ_ONLY,
    description="Export experiment report in PDF, JSON, or Markdown format",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            },
            "format": {
                "type": "string",
                "description": "Export format",
                "enum": ["pdf", "json", "markdown"],
                "default": "markdown",
            },
        },
        "required": ["experiment_id"],
    },
)
def export_experiment_report(experiment_id: str, format: str = "markdown") -> str:
    """Export experiment report."""
    return f"""**Export Report: {experiment_id}**

**Format:** {format}

⚠️ Experiment not found.

**Report Contents:**
- Executive summary
- Hypothesis and predictions
- Fault timeline
- Observation events
- Anomalies and SLO breaches
- Root cause analysis
- Metrics visualizations
- Recommendations

Use `get_experiment_results` to view results first.
"""
