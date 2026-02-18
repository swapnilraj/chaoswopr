"""Tests for the LLM client abstraction.

Tests MockLLMClient for deterministic testing and the factory function.
AnthropicLLMClient is tested for initialization behavior without
requiring actual API keys.
"""

from __future__ import annotations

import pytest

from chaoswopr.agents.llm_client import (
    AnthropicLLMClient,
    LLMResponse,
    MockLLMClient,
    create_llm_client,
)


class TestLLMResponse:
    """Tests for LLMResponse."""

    def test_default_response(self) -> None:
        response = LLMResponse()
        assert response.content == ""
        assert response.structured is None
        assert response.success is True
        assert response.error is None

    def test_error_response(self) -> None:
        response = LLMResponse(success=False, error="API error")
        assert not response.success
        assert response.error == "API error"

    def test_to_dict(self) -> None:
        response = LLMResponse(
            content="test",
            structured={"key": "value"},
            model="test-model",
            success=True,
        )
        d = response.to_dict()
        assert d["content"] == "test"
        assert d["structured"] == {"key": "value"}
        assert d["model"] == "test-model"
        assert d["success"] is True


class TestMockLLMClient:
    """Tests for MockLLMClient."""

    def test_is_available(self) -> None:
        client = MockLLMClient()
        assert client.is_available()

    def test_generate_returns_response(self) -> None:
        client = MockLLMClient()
        response = client.generate("Test prompt")
        assert response.success
        assert response.content != ""
        assert response.structured is not None
        assert response.model == "mock-llm-v1"

    def test_hypothesis_prompt_detection(self) -> None:
        client = MockLLMClient()
        response = client.generate(
            "Generate a hypothesis for this scenario with network latency fault"
        )
        assert response.success
        assert response.structured is not None
        assert "prediction" in response.structured
        assert "rationale" in response.structured
        assert "confidence" in response.structured

    def test_hypothesis_attestation_withholding(self) -> None:
        client = MockLLMClient()
        response = client.generate(
            "Generate a hypothesis for scenario with attestation withholding fault"
        )
        assert response.success
        assert "withholding" in response.structured["prediction"].lower() or \
               "finality" in response.structured["prediction"].lower()

    def test_rca_prompt_detection(self) -> None:
        client = MockLLMClient()
        response = client.generate(
            "Perform root cause analysis on finality anomaly events"
        )
        assert response.success
        assert "hypotheses" in response.structured
        assert len(response.structured["hypotheses"]) > 0
        hypothesis = response.structured["hypotheses"][0]
        assert "root_cause" in hypothesis
        assert "confidence" in hypothesis
        assert "recommendations" in hypothesis

    def test_analysis_prompt_detection(self) -> None:
        client = MockLLMClient()
        response = client.generate(
            "Analyze the following anomaly in consensus metrics"
        )
        assert response.success
        assert "summary" in response.structured
        assert "severity" in response.structured

    def test_generic_prompt(self) -> None:
        client = MockLLMClient()
        response = client.generate("What is the meaning of life?")
        assert response.success
        assert response.structured is not None

    def test_call_count_tracking(self) -> None:
        client = MockLLMClient()
        assert client.call_count == 0

        client.generate("Prompt 1")
        assert client.call_count == 1

        client.generate("Prompt 2")
        assert client.call_count == 2

    def test_prompt_history(self) -> None:
        client = MockLLMClient()
        client.generate("First prompt")
        client.generate("Second prompt")

        assert len(client.prompts) == 2
        assert client.prompts[0] == "First prompt"
        assert client.prompts[1] == "Second prompt"

    def test_usage_stats_in_response(self) -> None:
        client = MockLLMClient()
        response = client.generate("Test prompt for usage stats")
        assert "input_tokens" in response.usage
        assert "output_tokens" in response.usage
        assert response.usage["input_tokens"] > 0
        assert response.usage["output_tokens"] > 0


class TestAnthropicLLMClient:
    """Tests for AnthropicLLMClient initialization."""

    def test_unavailable_without_package(self) -> None:
        """Test that client handles missing anthropic package gracefully."""
        # The client should either work (if anthropic is installed)
        # or gracefully fail with is_available() = False
        client = AnthropicLLMClient(api_key="test-key")
        # We cannot guarantee anthropic is installed, so just check
        # that the client was created without raising
        assert isinstance(client, AnthropicLLMClient)

    def test_generate_when_unavailable(self) -> None:
        """Test that generate returns error when client is unavailable."""
        client = AnthropicLLMClient.__new__(AnthropicLLMClient)
        client._model = "test"
        client._max_retries = 1
        client._client = None
        client._available = False

        response = client.generate("Test prompt")
        assert not response.success
        assert "not available" in response.error


class TestCreateLLMClient:
    """Tests for the factory function."""

    def test_create_mock_client(self) -> None:
        client = create_llm_client(provider="mock")
        assert isinstance(client, MockLLMClient)
        assert client.is_available()

    def test_create_anthropic_client(self) -> None:
        client = create_llm_client(provider="anthropic", api_key="test-key")
        assert isinstance(client, AnthropicLLMClient)

    def test_create_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_client(provider="openai")

    def test_default_is_mock(self) -> None:
        client = create_llm_client()
        assert isinstance(client, MockLLMClient)
