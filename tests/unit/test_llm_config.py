"""Unit tests for LLM configuration management."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config.llm_config import LLMConfig


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_values(self) -> None:
        config = LLMConfig()
        assert config.provider == "mock"
        assert config.api_key == ""
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.hypothesis_model == "anthropic/claude-opus-4"
        assert config.rca_model == "anthropic/claude-sonnet-4.5"
        assert config.timeout_seconds == 60
        assert config.max_retries == 3
        assert config.dry_run is False

    def test_effective_provider_mock_when_dry_run(self) -> None:
        config = LLMConfig(provider="openrouter", dry_run=True)
        assert config.effective_provider == "mock"

    def test_effective_provider_returns_provider_when_not_dry_run(self) -> None:
        config = LLMConfig(provider="openrouter", dry_run=False)
        assert config.effective_provider == "openrouter"

    def test_validate_mock_provider(self) -> None:
        config = LLMConfig(provider="mock")
        errors = config.validate()
        assert errors == []

    def test_validate_openrouter_without_key(self) -> None:
        config = LLMConfig(provider="openrouter", api_key="")
        errors = config.validate()
        assert any("OPENROUTER_API_KEY" in e for e in errors)

    def test_validate_openrouter_with_key(self) -> None:
        config = LLMConfig(provider="openrouter", api_key="sk-or-v1-test")
        errors = config.validate()
        assert errors == []

    def test_validate_unknown_provider(self) -> None:
        config = LLMConfig(provider="unknown_provider")
        errors = config.validate()
        assert any("Unknown provider" in e for e in errors)

    def test_validate_invalid_timeout(self) -> None:
        config = LLMConfig(timeout_seconds=0)
        errors = config.validate()
        assert any("timeout_seconds" in e for e in errors)

    def test_validate_invalid_retries(self) -> None:
        config = LLMConfig(max_retries=-1)
        errors = config.validate()
        assert any("max_retries" in e for e in errors)


class TestLLMConfigFromEnv:
    """Tests for from_env class method."""

    def test_from_env_defaults(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = LLMConfig.from_env()
            assert config.provider == "mock"
            assert config.dry_run is False

    def test_from_env_openrouter(self) -> None:
        env = {
            "CHAOSWOPR_LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "sk-or-v1-test",
            "HYPOTHESIS_MODEL": "anthropic/claude-opus-4",
            "RCA_MODEL": "anthropic/claude-sonnet-4.5",
        }
        with patch.dict("os.environ", env, clear=True):
            config = LLMConfig.from_env()
            assert config.provider == "openrouter"
            assert config.api_key == "sk-or-v1-test"
            assert config.hypothesis_model == "anthropic/claude-opus-4"
            assert config.rca_model == "anthropic/claude-sonnet-4.5"

    def test_from_env_dry_run(self) -> None:
        with patch.dict("os.environ", {"CHAOSWOPR_DRY_RUN": "true"}, clear=True):
            config = LLMConfig.from_env()
            assert config.dry_run is True
            assert config.effective_provider == "mock"

    def test_from_env_dry_run_yes(self) -> None:
        with patch.dict("os.environ", {"CHAOSWOPR_DRY_RUN": "yes"}, clear=True):
            config = LLMConfig.from_env()
            assert config.dry_run is True

    def test_from_env_custom_timeout(self) -> None:
        with patch.dict("os.environ", {"OPENROUTER_TIMEOUT": "120"}, clear=True):
            config = LLMConfig.from_env()
            assert config.timeout_seconds == 120
