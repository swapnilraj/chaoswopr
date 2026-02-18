"""LLM configuration management for chaoswopr.

Centralizes all LLM-related configuration including:
  - Provider selection (openrouter, anthropic, mock)
  - API key management from environment variables
  - Model selection per use case (hypothesis, RCA)
  - Timeout and retry settings

Configuration priority:
  1. Explicit constructor arguments
  2. Environment variables
  3. Default values

Environment Variables:
  OPENROUTER_API_KEY: API key for OpenRouter (required for openrouter provider)
  CHAOSWOPR_LLM_PROVIDER: Provider name (openrouter, anthropic, mock)
  CHAOSWOPR_DRY_RUN: If "true", forces mock provider
  HYPOTHESIS_MODEL: Model for hypothesis generation
  RCA_MODEL: Model for root cause analysis
  OPENROUTER_BASE_URL: Override API base URL
  OPENROUTER_TIMEOUT: Request timeout in seconds
  OPENROUTER_MAX_RETRIES: Maximum retry attempts
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Configuration for LLM integrations.

    Attributes:
        provider: LLM provider name (openrouter, anthropic, mock).
        api_key: API key for the provider.
        base_url: API base URL.
        hypothesis_model: Model to use for hypothesis generation.
        rca_model: Model to use for root cause analysis.
        timeout_seconds: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        dry_run: If True, use mock provider regardless of other settings.
    """

    provider: str = "mock"
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    hypothesis_model: str = "anthropic/claude-opus-4"
    rca_model: str = "anthropic/claude-sonnet-4.5"
    timeout_seconds: int = 60
    max_retries: int = 3
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Create LLM configuration from environment variables.

        Returns:
            LLMConfig populated from environment.
        """
        dry_run = os.getenv("CHAOSWOPR_DRY_RUN", "false").lower() in ("true", "1", "yes")

        return cls(
            provider=os.getenv("CHAOSWOPR_LLM_PROVIDER", "mock"),
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            hypothesis_model=os.getenv("HYPOTHESIS_MODEL", "anthropic/claude-opus-4"),
            rca_model=os.getenv("RCA_MODEL", "anthropic/claude-sonnet-4.5"),
            timeout_seconds=int(os.getenv("OPENROUTER_TIMEOUT", "60")),
            max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "3")),
            dry_run=dry_run,
        )

    @property
    def effective_provider(self) -> str:
        """Get the effective provider, considering dry_run mode.

        Returns:
            'mock' if dry_run is True, otherwise the configured provider.
        """
        if self.dry_run:
            return "mock"
        return self.provider

    def validate(self) -> list[str]:
        """Validate the configuration.

        Returns:
            List of validation error messages. Empty means valid.
        """
        errors: list[str] = []

        if self.effective_provider == "openrouter" and not self.api_key:
            errors.append(
                "OPENROUTER_API_KEY is required when provider is 'openrouter'. "
                "Set it via environment variable or pass api_key explicitly."
            )

        if self.effective_provider == "anthropic" and not self.api_key:
            errors.append(
                "ANTHROPIC_API_KEY is required when provider is 'anthropic'."
            )

        if self.effective_provider not in ("openrouter", "anthropic", "mock"):
            errors.append(
                f"Unknown provider: {self.effective_provider}. "
                f"Supported: openrouter, anthropic, mock"
            )

        if self.timeout_seconds < 1:
            errors.append("timeout_seconds must be >= 1")

        if self.max_retries < 0:
            errors.append("max_retries must be >= 0")

        return errors
