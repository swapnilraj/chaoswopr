"""Unit tests for Root Cause Analysis (RCA) engine.

Tests LLM-based RCA using anomaly detection results, metrics, and RAG consultation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

import pytest

from chaoswopr.agents.anomaly_detection import Anomaly, AnomalyType
from chaoswopr.agents.observer import ObservationEvent, ObservationEventType
from chaoswopr.agents.rca_engine import (
    RCAEngine,
    RCAHypothesis,
    RCAResult,
)


class TestRCAHypothesis:
    """Tests for RCAHypothesis data class."""

    def test_creation(self) -> None:
        hypothesis = RCAHypothesis(
            root_cause="High finality delay due to network partition",
            confidence=0.85,
            evidence=["Metric spike in finality_delay", "Network latency increased"],
            recommendations=["Check network connectivity"],
        )
        assert hypothesis.root_cause.startswith("High finality")
        assert hypothesis.confidence == 0.85

    def test_to_dict(self) -> None:
        hypothesis = RCAHypothesis(
            root_cause="Test cause",
            confidence=0.9,
        )
        d = hypothesis.to_dict()
        assert d["root_cause"] == "Test cause"
        assert d["confidence"] == 0.9


class TestRCAResult:
    """Tests for RCAResult data class."""

    def test_creation(self) -> None:
        hypothesis = RCAHypothesis(root_cause="Test", confidence=0.8)
        result = RCAResult(
            hypotheses=[hypothesis],
            analysis_time_seconds=1.5,
        )
        assert len(result.hypotheses) == 1
        assert result.analysis_time_seconds == 1.5

    def test_to_dict(self) -> None:
        hypothesis = RCAHypothesis(root_cause="Test", confidence=0.8)
        result = RCAResult(hypotheses=[hypothesis])
        d = result.to_dict()
        assert "hypotheses" in d
        assert len(d["hypotheses"]) == 1


class TestRCAEngine:
    """Tests for RCA Engine."""

    def test_initialization(self) -> None:
        engine = RCAEngine(dry_run=True)
        assert engine.dry_run is True

    def test_analyze_no_events(self) -> None:
        """Should handle empty event list."""
        engine = RCAEngine(dry_run=True)
        result = engine.analyze(events=[], metrics={})
        # With no events, returns None (nothing to analyze)
        assert result is None

    def test_analyze_with_anomaly(self) -> None:
        """Should analyze anomaly events."""
        engine = RCAEngine(dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="finality_delay_seconds",
                severity="critical",
                details={"z_score": 4.5, "value": 700.0},
            )
        ]
        result = engine.analyze(events=events, metrics={"finality_delay_seconds": 700.0})
        assert result is not None
        assert "hypotheses" in result

    def test_analyze_with_slo_breach(self) -> None:
        """Should analyze SLO breach events."""
        engine = RCAEngine(dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.SLO_BREACH,
                timestamp=datetime.now(timezone.utc),
                metric_name="participation_rate_percent",
                severity="critical",
                details={"threshold": 66.0, "actual_value": 50.0},
            )
        ]
        result = engine.analyze(events=events, metrics={"participation_rate_percent": 50.0})
        assert result is not None

    def test_analyze_with_multiple_events(self) -> None:
        """Should handle multiple correlated events."""
        engine = RCAEngine(dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="finality_delay_seconds",
                details={"z_score": 4.0},
            ),
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="participation_rate_percent",
                details={"z_score": 3.5},
            ),
        ]
        result = engine.analyze(
            events=events,
            metrics={
                "finality_delay_seconds": 700.0,
                "participation_rate_percent": 50.0,
            },
        )
        assert result is not None
        # Should potentially identify correlation

    def test_analyze_with_rag(self) -> None:
        """Should consult RAG for context."""
        rag_pipeline = MagicMock()
        rag_pipeline.retrieve.return_value = [
            MagicMock(
                content="Finality delay can be caused by network partitions",
                relevance_score=0.9,
            )
        ]

        engine = RCAEngine(rag_pipeline=rag_pipeline, dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="finality_delay_seconds",
                details={"z_score": 4.0},
            )
        ]
        result = engine.analyze(events=events, metrics={"finality_delay_seconds": 700.0})
        assert result is not None
        # RAG should have been consulted
        assert rag_pipeline.retrieve.called

    def test_analyze_returns_confidence(self) -> None:
        """RCA should include confidence scores."""
        engine = RCAEngine(dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="test_metric",
                details={"z_score": 5.0},
            )
        ]
        result = engine.analyze(events=events, metrics={"test_metric": 100.0})
        assert result is not None
        if "hypotheses" in result and result["hypotheses"]:
            # Should have confidence scores
            assert "confidence" in result["hypotheses"][0]

    def test_get_stats(self) -> None:
        engine = RCAEngine(dry_run=True)
        stats = engine.get_stats()
        assert "total_analyses" in stats
        assert stats["total_analyses"] == 0

    def test_get_stats_after_analysis(self) -> None:
        engine = RCAEngine(dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="test",
            )
        ]
        engine.analyze(events=events, metrics={"test": 10.0})
        stats = engine.get_stats()
        assert stats["total_analyses"] == 1

    def test_dry_run_mode(self) -> None:
        """Dry run should not make real LLM calls."""
        engine = RCAEngine(dry_run=True)
        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="test",
            )
        ]
        # Should not raise even without LLM client
        result = engine.analyze(events=events, metrics={"test": 10.0})
        assert result is not None


class TestRCAEngineIntegration:
    """Integration tests with anomaly detection."""

    def test_analyze_anomaly_object(self) -> None:
        """Should work with Anomaly objects."""
        engine = RCAEngine(dry_run=True)

        # Create observation event from anomaly
        event = ObservationEvent(
            event_type=ObservationEventType.ANOMALY_DETECTED,
            timestamp=datetime.now(timezone.utc),
            metric_name="finality_delay_seconds",
            severity="critical",
            details={
                "anomaly_type": AnomalyType.Z_SCORE.value,
                "z_score": 5.0,
                "value": 800.0,
            },
        )

        result = engine.analyze(
            events=[event],
            metrics={"finality_delay_seconds": 800.0},
        )
        assert result is not None
