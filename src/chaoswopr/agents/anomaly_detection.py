"""Anomaly detection module for streaming metrics.

Implements three types of anomaly detection:
1. Z-score based detection: Detects metric values that deviate significantly from historical mean
2. Changepoint detection (CUSUM): Detects sudden regime shifts in metric values
3. Correlation detection: Detects when multiple metrics anomalously correlate

Used by the Observer Agent to identify issues in real-time during experiments.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnomalyType(str, Enum):
    """Type of anomaly detection."""

    Z_SCORE = "z_score"
    CHANGEPOINT = "changepoint"
    CORRELATION = "correlation"


@dataclass
class Anomaly:
    """An detected anomaly.

    Attributes:
        metric_name: Name of the metric with anomaly.
        anomaly_type: Type of anomaly detected.
        severity: Severity level (info, warning, critical).
        details: Additional details about the anomaly.
        timestamp: When the anomaly was detected (optional).
    """

    metric_name: str
    anomaly_type: AnomalyType
    severity: str = "warning"
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "metric_name": self.metric_name,
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class CorrelationAnomaly:
    """A detected correlation anomaly between metrics."""

    primary_metric: str
    correlated_metrics: list[str]
    correlation_strength: float
    severity: str = "info"


class AnomalyDetector:
    """Real-time anomaly detector for streaming metrics.

    Maintains a sliding window of metric history and detects anomalies using
    statistical methods. Designed for low-latency detection in production.

    Examples:
        >>> detector = AnomalyDetector(z_score_threshold=3.0)
        >>> # Build history
        >>> for i in range(30):
        ...     detector.update({"finality_delay": 13.0})
        >>> # Detect anomaly
        >>> anomalies = detector.detect({"finality_delay": 600.0})
        >>> if anomalies:
        ...     print(f"Detected {len(anomalies)} anomalies")
    """

    def __init__(
        self,
        z_score_threshold: float = 3.0,
        cusum_threshold: float = 10.0,
        correlation_threshold: float = 0.8,
        window_size: int = 30,
    ) -> None:
        """Initialize the anomaly detector.

        Args:
            z_score_threshold: Z-score threshold for anomaly detection.
            cusum_threshold: CUSUM threshold for changepoint detection.
            correlation_threshold: Correlation threshold for multi-metric anomalies.
            window_size: Size of sliding window for historical data.
        """
        self._z_score_threshold = z_score_threshold
        self._cusum_threshold = cusum_threshold
        self._correlation_threshold = correlation_threshold
        self._window_size = window_size

        # Metric history: metric_name -> deque of values
        self._metric_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

        # CUSUM state: metric_name -> cumulative sum
        self._cusum_state: dict[str, float] = defaultdict(float)

        # Stats
        self._total_updates = 0

    @property
    def z_score_threshold(self) -> float:
        """Get the z-score threshold."""
        return self._z_score_threshold

    @property
    def window_size(self) -> int:
        """Get the window size."""
        return self._window_size

    def update(self, metrics: dict[str, float]) -> None:
        """Update metric history with new values.

        Args:
            metrics: Dictionary of metric_name -> current_value.
        """
        for metric_name, value in metrics.items():
            self._metric_history[metric_name].append(value)

        self._total_updates += 1

    def detect(self, current_metrics: dict[str, float]) -> list[Anomaly]:
        """Detect anomalies in current metrics.

        Args:
            current_metrics: Dictionary of metric_name -> current_value.

        Returns:
            List of detected anomalies.
        """
        anomalies: list[Anomaly] = []

        # Update history first
        self.update(current_metrics)

        # Run detection methods
        for metric_name, value in current_metrics.items():
            # Z-score detection
            z_anomaly = self._detect_z_score(metric_name, value)
            if z_anomaly:
                anomalies.append(z_anomaly)

            # Changepoint detection (CUSUM)
            cp_anomaly = self._detect_changepoint(metric_name, value)
            if cp_anomaly:
                anomalies.append(cp_anomaly)

        # Correlation detection (across all metrics)
        corr_anomalies = self._detect_correlations(current_metrics)
        anomalies.extend(corr_anomalies)

        return anomalies

    def clear_history(self) -> None:
        """Clear all metric history."""
        self._metric_history.clear()
        self._cusum_state.clear()
        self._total_updates = 0

    def get_stats(self) -> dict[str, Any]:
        """Get detector statistics.

        Returns:
            Dictionary with detector stats.
        """
        return {
            "total_updates": self._total_updates,
            "metrics_tracked": list(self._metric_history.keys()),
            "window_size": self._window_size,
            "z_score_threshold": self._z_score_threshold,
            "cusum_threshold": self._cusum_threshold,
        }

    def _detect_z_score(self, metric_name: str, value: float) -> Anomaly | None:
        """Detect anomaly using z-score method.

        Args:
            metric_name: Name of the metric.
            value: Current value.

        Returns:
            Anomaly if detected, None otherwise.
        """
        history = self._metric_history.get(metric_name)
        if not history or len(history) < 10:
            # Need sufficient history
            return None

        # Calculate mean and stddev
        values = list(history)
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        stddev = math.sqrt(variance)

        if stddev == 0:
            # No variance, can't calculate z-score
            return None

        # Calculate z-score
        z_score = abs((value - mean) / stddev)

        if z_score > self._z_score_threshold:
            # Determine severity based on z-score magnitude
            if z_score > self._z_score_threshold * 2:
                severity = "critical"
            elif z_score > self._z_score_threshold * 1.5:
                severity = "warning"
            else:
                severity = "info"

            return Anomaly(
                metric_name=metric_name,
                anomaly_type=AnomalyType.Z_SCORE,
                severity=severity,
                details={
                    "z_score": z_score,
                    "threshold": self._z_score_threshold,
                    "value": value,
                    "mean": mean,
                    "stddev": stddev,
                },
            )

        return None

    def _detect_changepoint(self, metric_name: str, value: float) -> Anomaly | None:
        """Detect changepoint using CUSUM algorithm.

        Args:
            metric_name: Name of the metric.
            value: Current value.

        Returns:
            Anomaly if changepoint detected, None otherwise.
        """
        history = self._metric_history.get(metric_name)
        if not history or len(history) < 20:
            # Need sufficient history
            return None

        # Calculate baseline mean from first half of window
        baseline_values = list(history)[: len(history) // 2]
        baseline_mean = sum(baseline_values) / len(baseline_values)

        # CUSUM: cumulative sum of deviations from baseline
        deviation = value - baseline_mean
        self._cusum_state[metric_name] = max(
            0, self._cusum_state[metric_name] + deviation
        )

        if self._cusum_state[metric_name] > self._cusum_threshold:
            # Changepoint detected - reset CUSUM
            cusum_value = self._cusum_state[metric_name]
            self._cusum_state[metric_name] = 0

            return Anomaly(
                metric_name=metric_name,
                anomaly_type=AnomalyType.CHANGEPOINT,
                severity="warning",
                details={
                    "cusum_value": cusum_value,
                    "threshold": self._cusum_threshold,
                    "baseline_mean": baseline_mean,
                    "current_value": value,
                },
            )

        return None

    def _detect_correlations(
        self, current_metrics: dict[str, float]
    ) -> list[Anomaly]:
        """Detect correlation anomalies between metrics.

        When multiple metrics are anomalous simultaneously, check if they're
        correlated (e.g., CPU spike + participation drop).

        Args:
            current_metrics: Current metric values.

        Returns:
            List of correlation anomalies.
        """
        # This is a simplified correlation detector
        # In production, would calculate Pearson correlation over time windows
        anomalies: list[Anomaly] = []

        # For now, just detect when multiple metrics are simultaneously anomalous
        # (based on z-score detection)
        anomalous_metrics: list[str] = []

        for metric_name, value in current_metrics.items():
            history = self._metric_history.get(metric_name)
            if not history or len(history) < 10:
                continue

            values = list(history)
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            stddev = math.sqrt(variance) if variance > 0 else 0

            if stddev > 0:
                z_score = abs((value - mean) / stddev)
                if z_score > self._z_score_threshold:
                    anomalous_metrics.append(metric_name)

        # If multiple metrics are anomalous, flag as potential correlation
        if len(anomalous_metrics) >= 2:
            anomalies.append(
                Anomaly(
                    metric_name=",".join(anomalous_metrics),
                    anomaly_type=AnomalyType.CORRELATION,
                    severity="info",
                    details={
                        "correlated_metrics": anomalous_metrics,
                        "count": len(anomalous_metrics),
                    },
                )
            )

        return anomalies
