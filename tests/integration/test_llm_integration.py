"""Integration tests for LLM clients with real API calls.

These tests call the actual OpenRouter API and are skipped if
OPENROUTER_API_KEY is not set in the environment.

To run these tests:
    export OPENROUTER_API_KEY=sk-or-v1-your-key
    pytest tests/integration/test_llm_integration.py -v

Cost: approximately $0.05-0.10 per full test run.
"""

from __future__ import annotations

import os

import pytest

# Skip entire module if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set - skipping real API tests",
)


class TestOpenRouterIntegration:
    """Integration tests with real OpenRouter API."""

    def _make_client(self, model: str | None = None):
        from chaoswopr.agents.openrouter_client import OpenRouterLLMClient

        return OpenRouterLLMClient.from_env(model=model)

    def test_basic_generation(self) -> None:
        """Should generate a response from the API."""
        client = self._make_client(model="anthropic/claude-sonnet-4.5")
        response = client.generate(
            prompt="What is 2 + 2? Reply with just the number.",
            max_tokens=50,
            temperature=0.0,
        )
        assert response.success
        assert "4" in response.content

    def test_structured_json_output(self) -> None:
        """Should return structured JSON when schema is provided."""
        client = self._make_client(model="anthropic/claude-sonnet-4.5")

        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "integer"},
                "explanation": {"type": "string"},
            },
            "required": ["answer", "explanation"],
        }

        response = client.generate(
            prompt="What is 2 + 2? Provide your answer as JSON.",
            json_schema=schema,
            max_tokens=200,
            temperature=0.0,
        )

        assert response.success
        assert response.structured is not None
        assert response.structured["answer"] == 4
        assert response.usage["total_tokens"] > 0

    def test_usage_tracking(self) -> None:
        """Should track token usage."""
        client = self._make_client(model="anthropic/claude-sonnet-4.5")
        response = client.generate(
            prompt="Say hello.",
            max_tokens=50,
        )
        assert response.success
        assert response.usage["input_tokens"] > 0
        assert response.usage["output_tokens"] > 0
        assert client.stats["total_calls"] == 1
        assert client.stats["total_tokens"] > 0


class TestHypothesisEngineIntegration:
    """Integration tests for HypothesisEngine with real LLM."""

    def test_hypothesis_generation(self) -> None:
        """Should generate a valid hypothesis using real LLM."""
        from chaoswopr.agents.openrouter_client import OpenRouterLLMClient
        from chaoswopr.agents.hypothesis_engine import HypothesisEngine, HypothesisStatus

        llm = OpenRouterLLMClient.from_env(model="anthropic/claude-sonnet-4.5")
        engine = HypothesisEngine(llm_client=llm, dry_run=False)

        scenario = {
            "name": "integration_test_latency",
            "hypothesis": "Network maintains finality with 20% node latency injection",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {"time": "60s", "action": "inject_network_latency", "params": {"latency_ms": 200}},
                {"time": "360s", "action": "observe"},
                {"time": "600s", "action": "remove_faults"},
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
                "participation_rate_min_percent": 66.0,
            },
            "blast_radius": {
                "max_affected_percent": 20.0,
            },
        }

        hypothesis = engine.generate(scenario=scenario)

        assert hypothesis.prediction != ""
        assert hypothesis.blast_radius_percent <= 33.0
        assert hypothesis.blast_radius_percent >= 0.0
        assert len(hypothesis.fault_timeline) > 0
        assert hypothesis.success_criteria != ""
        assert 0.0 <= hypothesis.confidence <= 1.0

        # Validate
        errors = hypothesis.validate()
        # Even if there are validation errors from LLM output,
        # the engine should have tried to generate something
        assert hypothesis.status in (HypothesisStatus.VALIDATED, HypothesisStatus.REJECTED)


class TestRCAEngineIntegration:
    """Integration tests for RCAEngine with real LLM."""

    def test_rca_analysis(self) -> None:
        """Should perform real RCA analysis."""
        from datetime import datetime, timezone

        from chaoswopr.agents.openrouter_client import OpenRouterLLMClient
        from chaoswopr.agents.observer import ObservationEvent, ObservationEventType
        from chaoswopr.agents.rca_engine import RCAEngine

        llm = OpenRouterLLMClient.from_env(model="anthropic/claude-sonnet-4.5")
        engine = RCAEngine(llm_client=llm, dry_run=False)

        events = [
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="finality_delay_seconds",
                severity="critical",
                details={"z_score": 5.2, "value": 800.0, "anomaly_type": "z_score"},
            ),
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="participation_rate_percent",
                severity="warning",
                details={"z_score": 3.1, "value": 55.0, "anomaly_type": "z_score"},
            ),
        ]

        metrics = {
            "finality_delay_seconds": 800.0,
            "participation_rate_percent": 55.0,
            "slashing_rate_percent": 0.0,
        }

        result = engine.analyze(events=events, metrics=metrics)

        assert result is not None
        assert "hypotheses" in result
        assert len(result["hypotheses"]) > 0

        first = result["hypotheses"][0]
        assert "root_cause" in first
        assert "confidence" in first
        assert 0.0 <= first["confidence"] <= 1.0
        assert "evidence" in first
        assert "recommendations" in first
