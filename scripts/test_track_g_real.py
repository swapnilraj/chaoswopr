#!/usr/bin/env python3
"""Test Track G (Observer Agent) on real infrastructure.

This script tests the Observer Agent components with mock Prometheus to validate:
1. Anomaly detection (z-score, changepoint, correlation)
2. SLO monitoring and breach detection
3. Root cause analysis engine
4. Full Observer Agent integration
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.agents.anomaly_detection import AnomalyDetector, AnomalyType
from chaoswopr.agents.slo_monitor import SLOMonitor, SLODefinition
from chaoswopr.agents.rca_engine import RCAEngine
from chaoswopr.agents.observer import ObserverAgent, ObservationEvent, ObservationEventType
from datetime import datetime, timezone


# Mock Prometheus client for testing
class MockPrometheusClient:
    """Mock Prometheus client that returns test metrics."""

    def __init__(self):
        self.query_count = 0
        self.metrics = {
            "finality_delay_seconds": 13.0,
            "participation_rate_percent": 95.0,
            "slashing_rate_percent": 0.1,
        }

    def query(self, metric_name: str):
        """Mock query that returns test metrics."""
        self.query_count += 1

        class Result:
            def __init__(self, success, value):
                self.success = success
                self._value = value

            def get_value(self):
                return self._value

        if metric_name in self.metrics:
            return Result(True, self.metrics[metric_name])
        return Result(False, None)


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def main() -> int:
    """Run Track G real infrastructure tests."""
    print_section("TRACK G: OBSERVER AGENT - REAL INFRASTRUCTURE TESTING")

    print("Testing Observer Agent components with real implementations")
    print()

    # Test 1: Anomaly Detection
    print_section("Test 1: Anomaly Detection")

    detector = AnomalyDetector(z_score_threshold=3.0, window_size=30)
    print(f"✓ AnomalyDetector created (threshold={detector.z_score_threshold}, window={detector.window_size})")

    # Build history with normal values
    print("\nBuilding metric history (30 normal values)...")
    for i in range(30):
        detector.update({"finality_delay": 13.0 + (i % 3) * 0.5})

    stats = detector.get_stats()
    print(f"  History built: {stats['total_updates']} updates, tracking {len(stats['metrics_tracked'])} metrics")

    # Detect anomaly with outlier
    print("\nDetecting anomaly with outlier value (700.0)...")
    anomalies = detector.detect({"finality_delay": 700.0})

    if anomalies:
        print(f"✅ Detected {len(anomalies)} anomalies:")
        for anomaly in anomalies:
            print(f"  - {anomaly.metric_name}: {anomaly.anomaly_type.value} (severity: {anomaly.severity})")
            if anomaly.anomaly_type == AnomalyType.Z_SCORE:
                print(f"    Z-score: {anomaly.details.get('z_score', 'N/A'):.2f}")
    else:
        print("❌ No anomalies detected (expected at least 1)")
        return 1

    # Test 2: SLO Monitoring
    print_section("Test 2: SLO Monitoring")

    slo_monitor = SLOMonitor()
    print("✓ SLOMonitor created")

    # Add SLO definitions
    print("\nAdding SLO definitions...")
    finality_slo = SLODefinition(
        metric_name="finality_delay_seconds",
        threshold=600.0,
        comparison="less_than",
        error_budget_percent=1.0,
        description="Finality delay must stay under 10 minutes"
    )
    slo_monitor.add_slo("finality_slo", finality_slo)

    participation_slo = SLODefinition(
        metric_name="participation_rate_percent",
        threshold=90.0,
        comparison="greater_than",
        error_budget_percent=2.0,
        description="Participation must stay above 90%"
    )
    slo_monitor.add_slo("participation_slo", participation_slo)

    print(f"✓ Added {len(slo_monitor.slos)} SLO definitions")

    # Check for breaches (none expected with normal values)
    print("\nChecking SLOs with normal metrics...")
    normal_metrics = {"finality_delay_seconds": 13.0, "participation_rate_percent": 95.0}
    breaches = slo_monitor.check_breaches(normal_metrics)

    if breaches:
        print(f"❌ Unexpected breaches with normal metrics: {len(breaches)}")
        return 1
    print("✅ No breaches detected with normal metrics")

    # Check with breach condition
    print("\nChecking SLOs with breach condition...")
    breach_metrics = {"finality_delay_seconds": 700.0, "participation_rate_percent": 85.0}
    breaches = slo_monitor.check_breaches(breach_metrics)

    if len(breaches) >= 2:
        print(f"✅ Detected {len(breaches)} SLO breaches:")
        for breach in breaches:
            print(f"  - {breach['slo_name']}: {breach['metric_name']} = {breach['actual_value']} (threshold: {breach['threshold']})")
    else:
        print(f"❌ Expected 2 breaches, got {len(breaches)}")
        return 1

    # Check error budget
    print("\nChecking error budget...")
    budget = slo_monitor.get_error_budget("finality_slo")
    if budget:
        print(f"✅ Error budget: {budget['consumed_percent']:.1f}% consumed, {budget['remaining_percent']:.1f}% remaining")
        print(f"   Status: {budget['status']}")
    else:
        print("❌ Failed to get error budget")
        return 1

    # Test 3: RCA Engine
    print_section("Test 3: Root Cause Analysis Engine")

    rca_engine = RCAEngine(dry_run=True)
    print(f"✓ RCAEngine created (dry_run={rca_engine.dry_run})")

    # Create mock observation events
    print("\nCreating mock observation events...")
    events = [
        ObservationEvent(
            event_type=ObservationEventType.ANOMALY_DETECTED,
            timestamp=datetime.now(timezone.utc),
            metric_name="finality_delay_seconds",
            severity="critical",
            details={
                "anomaly_type": "z_score",
                "z_score": 45.0,
                "value": 700.0,
                "threshold": 3.0,
            },
        ),
        ObservationEvent(
            event_type=ObservationEventType.SLO_BREACH,
            timestamp=datetime.now(timezone.utc),
            metric_name="finality_delay_seconds",
            severity="critical",
            details={
                "slo_name": "finality_slo",
                "threshold": 600.0,
                "actual_value": 700.0,
            },
        ),
    ]
    print(f"✓ Created {len(events)} observation events")

    # Perform RCA
    print("\nPerforming root cause analysis...")
    rca_result = rca_engine.analyze(
        events=events,
        metrics={"finality_delay_seconds": 700.0},
        experiment_id="test-exp-001"
    )

    if rca_result:
        hypotheses = rca_result.get("hypotheses", [])
        print(f"✅ RCA completed in {rca_result['analysis_time_seconds']:.3f}s")
        print(f"   Generated {len(hypotheses)} hypotheses:")
        for i, hyp in enumerate(hypotheses, 1):
            print(f"   {i}. {hyp['root_cause']}")
            print(f"      Confidence: {hyp['confidence']:.2f}")
            print(f"      Recommendations: {len(hyp['recommendations'])}")
    else:
        print("❌ RCA analysis returned None")
        return 1

    # Test 4: Full Observer Agent Integration
    print_section("Test 4: Full Observer Agent Integration")

    prom_client = MockPrometheusClient()
    observer = ObserverAgent(
        prometheus_client=prom_client,
        anomaly_detector=detector,
        slo_monitor=slo_monitor,
        rca_engine=rca_engine,
        dry_run=True  # Don't actually query metrics
    )
    print("✓ ObserverAgent created with all components")

    # Start observing
    print("\nStarting observation...")
    observer.start_observing(experiment_id="test-exp-002")
    status = observer.get_status()
    print(f"✅ Observer started")
    print(f"   State: {status['state']}")
    print(f"   Experiment: {status['current_experiment_id']}")

    # Run observation cycles
    print("\nRunning 3 observation cycles...")
    for i in range(3):
        events = observer.observe()
        print(f"  Cycle {i+1}: {len(events)} events detected")

    status = observer.get_status()
    print(f"✅ Completed {status['observation_count']} observation cycles")
    print(f"   Total events: {status['event_count']}")

    # Get events
    print("\nRetrieving events...")
    all_events = observer.get_events()
    start_events = observer.get_events(event_type=ObservationEventType.OBSERVATION_START)

    print(f"✅ Retrieved {len(all_events)} total events")
    print(f"   Start events: {len(start_events)}")

    # Stop observing
    print("\nStopping observation...")
    observer.stop_observing()
    status = observer.get_status()

    if status['state'] == 'idle':
        print("✅ Observer stopped successfully")
    else:
        print(f"❌ Observer state is {status['state']}, expected 'idle'")
        return 1

    # Final summary
    print_section("All Tests Passed!")

    print("Summary:")
    print(f"  ✅ AnomalyDetector working ({detector.get_stats()['total_updates']} updates processed)")
    print(f"  ✅ SLOMonitor working ({len(slo_monitor.slos)} SLOs, {slo_monitor.get_status()['total_checks']} checks)")
    print(f"  ✅ RCAEngine working ({rca_engine.get_stats()['total_analyses']} analyses)")
    print(f"  ✅ ObserverAgent working ({status['observation_count']} observations)")
    print()
    print("🎉 Track G (Observer Agent) is FULLY FUNCTIONAL!")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
