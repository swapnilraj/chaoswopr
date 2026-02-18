"""LLM client abstraction for chaoswopr agent system.

Provides a unified interface for LLM interactions used by:
  - HypothesisEngine: Generating structured hypotheses from scenarios
  - RCAEngine: Root cause analysis from observation events
  - Observer Agent: Anomaly interpretation and context retrieval

Supports multiple backends:
  - MockLLMClient: Deterministic template-based responses (testing/dry-run)
  - AnthropicLLMClient: Claude API integration (production)

The client always returns structured JSON for deterministic downstream
processing. In production mode, prompts include JSON schema constraints
and output is validated before returning.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from an LLM call.

    Attributes:
        content: Raw text content from the LLM.
        structured: Parsed JSON content (if applicable).
        model: Model identifier used.
        usage: Token usage statistics.
        success: Whether the call succeeded.
        error: Error message if failed.
    """

    content: str = ""
    structured: dict[str, Any] | None = None
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "structured": self.structured,
            "model": self.model,
            "usage": self.usage,
            "success": self.success,
            "error": self.error,
        }


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: User prompt.
            system_prompt: System prompt for context.
            json_schema: Expected JSON output schema.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).

        Returns:
            LLMResponse with content.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM client is available and configured."""


class MockLLMClient(LLMClient):
    """Mock LLM client for testing and dry-run mode.

    Returns deterministic responses based on prompt content analysis.
    Useful for unit tests and demos without real API calls.

    Examples:
        >>> client = MockLLMClient()
        >>> response = client.generate("Generate a hypothesis for network latency test")
        >>> assert response.success
        >>> assert response.structured is not None
    """

    def __init__(self) -> None:
        """Initialize the mock client."""
        self._call_count = 0
        self._prompts: list[str] = []

    @property
    def call_count(self) -> int:
        """Get the number of LLM calls made."""
        return self._call_count

    @property
    def prompts(self) -> list[str]:
        """Get all prompts sent to this client."""
        return self._prompts

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Generate a mock response based on prompt content.

        Analyzes the prompt to determine what kind of response to generate,
        then returns a structured mock response.

        Args:
            prompt: User prompt.
            system_prompt: System prompt (logged but not used).
            json_schema: Expected JSON schema (used to shape response).
            max_tokens: Maximum tokens (not used).
            temperature: Temperature (not used).

        Returns:
            LLMResponse with mock structured content.
        """
        self._call_count += 1
        self._prompts.append(prompt)

        prompt_lower = prompt.lower()

        # Detect prompt type and generate appropriate response
        if "hypothesis" in prompt_lower and ("scenario" in prompt_lower or "fault" in prompt_lower):
            structured = self._mock_hypothesis_response(prompt_lower)
        elif "root cause" in prompt_lower or "rca" in prompt_lower:
            structured = self._mock_rca_response(prompt_lower)
        elif "anomaly" in prompt_lower or "analyze" in prompt_lower:
            structured = self._mock_analysis_response(prompt_lower)
        else:
            structured = self._mock_generic_response(prompt_lower)

        content = json.dumps(structured, indent=2)

        return LLMResponse(
            content=content,
            structured=structured,
            model="mock-llm-v1",
            usage={"input_tokens": len(prompt.split()), "output_tokens": len(content.split())},
            success=True,
        )

    def is_available(self) -> bool:
        """Mock client is always available."""
        return True

    def _mock_hypothesis_response(self, prompt: str) -> dict[str, Any]:
        """Generate a mock hypothesis response."""
        if "latency" in prompt or "network" in prompt:
            return {
                "prediction": "The Ethereum testnet will maintain finality with degraded latency",
                "rationale": "Consensus protocols tolerate network delays below slot time (12s)",
                "blast_radius_percent": 20.0,
                "confidence": 0.8,
                "success_criteria": "Finality maintained with increased attestation inclusion delay",
                "failure_criteria": "Finality delay exceeds 5 epochs",
                "expected_recovery_seconds": 180,
            }
        elif "withholding" in prompt or "attestation" in prompt:
            return {
                "prediction": "Finality will experience delay but eventually recover with 30% attestation withholding",
                "rationale": "Below the 2/3 threshold, finality stalls. Above it, continues with degraded performance",
                "blast_radius_percent": 30.0,
                "confidence": 0.75,
                "success_criteria": "Finality recovers within 5 minutes after fault removal",
                "failure_criteria": "Finality delay exceeds 10 minutes or slashing occurs",
                "expected_recovery_seconds": 300,
            }
        else:
            return {
                "prediction": "System maintains operational status under tested fault conditions",
                "rationale": "Ethereum consensus design provides fault tolerance",
                "blast_radius_percent": 10.0,
                "confidence": 0.7,
                "success_criteria": "All SLOs maintained within thresholds",
                "failure_criteria": "Any SLO breach detected",
                "expected_recovery_seconds": 120,
            }

    def _mock_rca_response(self, prompt: str) -> dict[str, Any]:
        """Generate a mock RCA response."""
        hypotheses = []

        if "finality" in prompt:
            hypotheses.append({
                "root_cause": "High finality delay caused by reduced validator participation",
                "confidence": 0.85,
                "evidence": [
                    "Finality delay increased beyond 2 epochs",
                    "Participation rate dropped below 80%",
                ],
                "recommendations": [
                    "Check network connectivity between validator nodes",
                    "Verify validator client synchronization status",
                    "Review attestation submission patterns",
                ],
            })

        if "participation" in prompt or "validator" in prompt:
            hypotheses.append({
                "root_cause": "Low participation rate due to validator client resource exhaustion",
                "confidence": 0.7,
                "evidence": [
                    "Participation rate anomaly detected",
                    "CPU/memory metrics elevated on affected nodes",
                ],
                "recommendations": [
                    "Check validator node resource utilization",
                    "Verify beacon chain head tracking",
                    "Inspect P2P gossip message propagation",
                ],
            })

        if not hypotheses:
            hypotheses.append({
                "root_cause": "Anomaly requires further investigation",
                "confidence": 0.5,
                "evidence": ["Metric deviation detected beyond normal thresholds"],
                "recommendations": [
                    "Review correlated metrics for patterns",
                    "Check infrastructure component health",
                ],
            })

        return {"hypotheses": hypotheses}

    def _mock_analysis_response(self, prompt: str) -> dict[str, Any]:
        """Generate a mock analysis response."""
        return {
            "summary": "Metric anomaly detected during experiment execution",
            "severity": "warning",
            "affected_components": ["consensus_layer", "validator_clients"],
            "correlation_score": 0.82,
            "recommendations": [
                "Continue monitoring",
                "Review detailed metric time series",
            ],
        }

    def _mock_generic_response(self, prompt: str) -> dict[str, Any]:
        """Generate a generic mock response."""
        return {
            "response": "Analysis complete",
            "details": "Mock response generated for testing purposes",
        }


class AnthropicLLMClient(LLMClient):
    """LLM client using Anthropic's Claude API.

    Requires the anthropic package to be installed and an API key
    configured via the ANTHROPIC_API_KEY environment variable.

    Examples:
        >>> client = AnthropicLLMClient(api_key="sk-...")  # doctest: +SKIP
        >>> response = client.generate("Test prompt")  # doctest: +SKIP
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
    ) -> None:
        """Initialize the Anthropic client.

        Args:
            api_key: API key (or set ANTHROPIC_API_KEY env var).
            model: Model identifier to use.
            max_retries: Maximum retries on failure.
        """
        self._model = model
        self._max_retries = max_retries
        self._client = None
        self._available = False

        try:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=api_key,
                max_retries=max_retries,
            )
            self._available = True
            logger.info("Anthropic client initialized (model=%s)", model)
        except ImportError:
            logger.warning(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )
        except Exception as e:
            logger.warning("Failed to initialize Anthropic client: %s", e)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Generate a response using Claude.

        Args:
            prompt: User prompt.
            system_prompt: System prompt for context.
            json_schema: Expected JSON output schema (added to prompt).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content.
        """
        if not self._available or self._client is None:
            return LLMResponse(
                success=False,
                error="Anthropic client not available",
            )

        # Build prompt with JSON schema instruction if provided
        full_prompt = prompt
        if json_schema:
            schema_str = json.dumps(json_schema, indent=2)
            full_prompt += (
                f"\n\nRespond with valid JSON matching this schema:\n"
                f"```json\n{schema_str}\n```"
            )

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "You are an expert Ethereum consensus layer engineer analyzing chaos engineering experiments.",
                messages=[
                    {"role": "user", "content": full_prompt},
                ],
            )

            content = message.content[0].text
            usage = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }

            # Try to parse as JSON
            structured = None
            try:
                # Handle content that might have markdown code blocks
                json_content = content
                if "```json" in json_content:
                    json_content = json_content.split("```json")[1].split("```")[0].strip()
                elif "```" in json_content:
                    json_content = json_content.split("```")[1].split("```")[0].strip()
                structured = json.loads(json_content)
            except (json.JSONDecodeError, IndexError):
                logger.debug("LLM response is not JSON, returning raw content")

            return LLMResponse(
                content=content,
                structured=structured,
                model=self._model,
                usage=usage,
                success=True,
            )

        except Exception as e:
            logger.error("Anthropic API call failed: %s", e)
            return LLMResponse(
                success=False,
                error=str(e),
                model=self._model,
            )

    def is_available(self) -> bool:
        """Check if the Anthropic client is available."""
        return self._available


def create_llm_client(
    provider: str = "mock",
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout_seconds: int = 60,
    max_retries: int = 3,
) -> LLMClient:
    """Factory function to create an LLM client.

    Args:
        provider: Client provider ("mock", "anthropic", "openrouter").
        api_key: API key for the provider.
        model: Model identifier.
        base_url: API base URL (for openrouter provider).
        timeout_seconds: Request timeout (for openrouter provider).
        max_retries: Maximum retries (for openrouter provider).

    Returns:
        LLMClient instance.

    Raises:
        ValueError: If provider is not supported or required config is missing.
    """
    if provider == "mock":
        return MockLLMClient()
    elif provider == "anthropic":
        return AnthropicLLMClient(
            api_key=api_key,
            model=model or "claude-sonnet-4-20250514",
        )
    elif provider == "openrouter":
        from chaoswopr.agents.openrouter_client import OpenRouterLLMClient

        if not api_key:
            raise ValueError(
                "api_key is required for openrouter provider. "
                "Set OPENROUTER_API_KEY environment variable or pass api_key."
            )
        return OpenRouterLLMClient(
            api_key=api_key,
            model=model or "anthropic/claude-opus-4",
            base_url=base_url or "https://openrouter.ai/api/v1",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. Supported: mock, anthropic, openrouter"
        )


def create_llm_client_from_config() -> LLMClient:
    """Create an LLM client from environment-based configuration.

    Uses the LLMConfig to read environment variables and create the
    appropriate client. Falls back to MockLLMClient if configuration
    is invalid or incomplete.

    Returns:
        Configured LLMClient instance.
    """
    try:
        from config.llm_config import LLMConfig
    except ImportError:
        logger.debug("config.llm_config not available, using mock client")
        return MockLLMClient()

    config = LLMConfig.from_env()
    errors = config.validate()

    if errors:
        logger.warning(
            "LLM config validation errors, falling back to mock: %s",
            errors,
        )
        return MockLLMClient()

    return create_llm_client(
        provider=config.effective_provider,
        api_key=config.api_key,
        model=config.hypothesis_model,
        base_url=config.base_url,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
    )
