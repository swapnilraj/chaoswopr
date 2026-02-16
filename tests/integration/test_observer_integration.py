"""Integration tests for Observer Agent with all components.

Tests the full integration of ObserverAgent with anomaly detection,
SLO monitoring, RAG pipeline, and RCA engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from chaoswopr.agents import (
    AnomalyDetector,
    ObservationEventType,
    ObserverAgent,
    RAGPipeline,
    RCAEngine,
    SLODefinition,
    SLOMonitor,
)
from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient


@pytest.mark.integration
class TestObserverIntegration:
    """Integration tests for Observer Agent."""

    def test_full_observation_cycle(self) -> None:
        """Test complete observation cycle with all components."""
        # Set up Prometheus client mock
        prom_client = MagicMock(spec=PrometheusClient)

        # Create a mock query result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.get_value.return_value = 700.0  # High finality delay
        prom_client.query.return_value = mock_result

        # Create Observer with all components
        anomaly_detector = AnomalyDetector(z_score_threshold=3.0)
        slo_monitor = SLOMonitor()
        rag_pipeline = RAGPipeline(dry_run=True)
        rca_engine = RCAEngine(rag_pipeline=rag_pipeline, dry_run=True)

        observer = ObserverAgent(
            prometheus_client=prom_client,
            anomaly_detector=anomaly_detector,
            slo_monitor=slo_monitor,
            rca_engine=rca_engine,
            dry_run=False,  # Actually query Prometheus (mock)
        )

        # Configure SLO
        slo_monitor.add_slo(
            "finality_slo",
            SLODefinition(
                metric_name="finality_delay_seconds",
                threshold=600.0,
                comparison="less_than",
            ),
        )

        # Index some documents in RAG
        from chaoswopr.agents.rag_pipeline import Document

        rag_pipeline.index_documents([
            Document(
                content="Finality delays can be caused by network partitions or validator issues",
                source="ethereum-docs",
            ),
        ])

        # Build anomaly detector history (baseline)
        for i in range(30):
            anomaly_detector.update({"finality_delay_seconds": 13.0})

        # Start observing
        observer.start_observing(experiment_id="integration-test-001")

        # Run observation cycle
        events = observer.observe()

        # Should detect:
        # 1. Anomaly (700.0 vs baseline 13.0)
        # 2. SLO breach (700.0 > 600.0)
        # 3. Potentially RCA hypothesis
        assert len(events) > 0

        # Check for SLO breach event
        slo_breaches = [
            e for e in events if e.event_type == ObservationEventType.SLO_BREACH
        ]
        assert len(slo_breaches) >= 1
        assert slo_breaches[0].metric_name == "finality_delay_seconds"

        # Check for anomaly detection event
        anomalies = [
            e for e in events if e.event_type == ObservationEventType.ANOMALY_DETECTED
        ]
        assert len(anomalies) >= 1

        # Check observer status
        status = observer.get_status()
        assert status["state"] == "observing"
        assert status["observation_count"] == 1
        assert status["current_experiment_id"] == "integration-test-001"

        # Stop observing
        observer.stop_observing()

        # Verify observation end event was recorded
        all_events = observer.get_events(experiment_id="integration-test-001")
        end_events = [
            e for e in all_events
            if e.event_type == ObservationEventType.OBSERVATION_END
        ]
        assert len(end_events) == 1

    def test_observer_auto_creates_components(self) -> None:
        """Observer should auto-create components if not provided."""
        prom_client = MagicMock(spec=PrometheusClient)
        observer = ObserverAgent(prometheus_client=prom_client, dry_run=True)

        # Components should be auto-created
        assert observer._anomaly_detector is not None
        assert observer._slo_monitor is not None
        assert observer._rca_engine is not None

    def test_observer_handles_multiple_experiments(self) -> None:
        """Observer should track events per experiment."""
        prom_client = MagicMock(spec=PrometheusClient)
        prom_client.query.return_value = MagicMock(success=True, data=[])

        observer = ObserverAgent(prometheus_client=prom_client, dry_run=True)

        # Observe first experiment
        observer.start_observing(experiment_id="exp-001")
        observer.observe()
        observer.stop_observing()

        # Observe second experiment
        observer.start_observing(experiment_id="exp-002")
        observer.observe()
        observer.stop_observing()

        # Should be able to filter events by experiment
        exp1_events = observer.get_events(experiment_id="exp-001")
        exp2_events = observer.get_events(experiment_id="exp-002")

        assert len(exp1_events) > 0
        assert len(exp2_events) > 0
        assert all(e.experiment_id == "exp-001" for e in exp1_events)
        assert all(e.experiment_id == "exp-002" for e in exp2_events)

    def test_observer_error_budget_tracking(self) -> None:
        """Observer should track error budgets across observations."""
        prom_client = MagicMock(spec=PrometheusClient)

        # Configure SLO with error budget
        slo_monitor = SLOMonitor()
        slo_monitor.add_slo(
            "test_slo",
            SLODefinition(
                metric_name="test_metric",
                threshold=100.0,
                comparison="less_than",
                error_budget_percent=5.0,  # 5% error budget
            ),
        )

        # Directly test error budget tracking without full observer
        # Simulate observations: 95 good, 5 bad (5% breach rate)
        for i in range(100):
            value = 150.0 if i < 5 else 50.0
            slo_monitor.check_breaches({"test_metric": value})

        # Check error budget
        budget = slo_monitor.get_error_budget("test_slo")
        assert budget is not None
        assert budget["consumed_percent"] == pytest.approx(5.0, abs=0.1)
        assert budget["status"] in ["compliant", "warning"]  # At edge of budget
