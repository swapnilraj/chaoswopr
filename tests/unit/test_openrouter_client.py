"""Unit tests for the OpenRouter LLM client.

Tests HTTP request formatting, response parsing, retry logic, and error handling
using mocked HTTP responses. No real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from chaoswopr.agents.openrouter_client import (
    OpenRouterAPIError,
    OpenRouterLLMClient,
)


class TestOpenRouterLLMClientInit:
    """Tests for OpenRouterLLMClient initialization."""

    def test_initialization(self) -> None:
        client = OpenRouterLLMClient(api_key="sk-or-v1-test")
        assert client.is_available()
        assert client.model == "anthropic/claude-opus-4"

    def test_custom_model(self) -> None:
        client = OpenRouterLLMClient(
            api_key="sk-or-v1-test",
            model="anthropic/claude-sonnet-4.5",
        )
        assert client.model == "anthropic/claude-sonnet-4.5"

    def test_empty_api_key_not_available(self) -> None:
        client = OpenRouterLLMClient(api_key="")
        assert not client.is_available()

    def test_stats_initially_zero(self) -> None:
        client = OpenRouterLLMClient(api_key="sk-or-v1-test")
        stats = client.stats
        assert stats["total_calls"] == 0
        assert stats["total_tokens"] == 0
        assert stats["total_errors"] == 0


class TestOpenRouterLLMClientGenerate:
    """Tests for the generate method with mocked HTTP."""

    def _make_client(self) -> OpenRouterLLMClient:
        """Create a client with a mocked session."""
        client = OpenRouterLLMClient(
            api_key="sk-or-v1-test",
            model="anthropic/claude-opus-4",
            max_retries=1,
        )
        return client

    def _mock_response(
        self,
        content: str | dict,
        status_code: int = 200,
        usage: dict | None = None,
    ) -> Mock:
        """Create a mock HTTP response."""
        mock_resp = Mock()
        mock_resp.status_code = status_code

        if isinstance(content, dict):
            content_str = json.dumps(content)
        else:
            content_str = content

        if status_code == 200:
            response_body = {
                "choices": [
                    {"message": {"content": content_str}}
                ],
                "usage": usage or {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
                "model": "anthropic/claude-opus-4",
            }
        else:
            response_body = {
                "error": {"message": f"Error {status_code}"}
            }

        mock_resp.json.return_value = response_body
        mock_resp.text = json.dumps(response_body)
        return mock_resp

    def test_successful_json_response(self) -> None:
        """Should parse JSON response correctly."""
        client = self._make_client()

        hypothesis = {
            "prediction": "Network maintains finality",
            "blast_radius_percent": 20,
            "confidence": 0.8,
        }
        mock_resp = self._mock_response(hypothesis)

        with patch.object(client._session, "post", return_value=mock_resp):
            response = client.generate(
                prompt="Generate hypothesis",
                system_prompt="You are an expert",
                json_schema={"type": "object"},
            )

        assert response.success
        assert response.structured is not None
        assert response.structured["prediction"] == "Network maintains finality"
        assert response.structured["blast_radius_percent"] == 20
        assert response.usage["total_tokens"] == 150
        assert client.stats["total_calls"] == 1

    def test_raw_text_response(self) -> None:
        """Should handle non-JSON text responses."""
        client = self._make_client()

        mock_resp = self._mock_response("This is a plain text response")

        with patch.object(client._session, "post", return_value=mock_resp):
            response = client.generate(prompt="Explain something")

        assert response.success
        assert response.content == "This is a plain text response"
        assert response.structured is None

    def test_json_in_code_block(self) -> None:
        """Should extract JSON from markdown code blocks."""
        client = self._make_client()

        content_with_block = '```json\n{"prediction": "test"}\n```'
        mock_resp = self._mock_response(content_with_block)

        with patch.object(client._session, "post", return_value=mock_resp):
            response = client.generate(prompt="Generate")

        assert response.success
        assert response.structured is not None
        assert response.structured["prediction"] == "test"

    def test_request_format(self) -> None:
        """Should format the API request correctly."""
        client = self._make_client()

        mock_resp = self._mock_response({"result": "ok"})

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.generate(
                prompt="Test prompt",
                system_prompt="System prompt",
                temperature=0.7,
                max_tokens=1000,
            )

        # Verify the request was made correctly
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        assert body["model"] == "anthropic/claude-opus-4"
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 1000
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "System prompt"
        assert body["messages"][1]["role"] == "user"

    def test_model_override(self) -> None:
        """Should use model override when specified."""
        client = self._make_client()

        mock_resp = self._mock_response({"result": "ok"})

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.generate(
                prompt="Test",
                model="anthropic/claude-sonnet-4.5",
            )

        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["model"] == "anthropic/claude-sonnet-4.5"

    def test_json_schema_appended_to_prompt(self) -> None:
        """Should append JSON schema to the prompt."""
        client = self._make_client()

        mock_resp = self._mock_response({"result": "ok"})
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.generate(
                prompt="Generate something",
                json_schema=schema,
            )

        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        user_msg = body["messages"][-1]["content"]
        assert "json" in user_msg.lower()
        assert "response_format" in body
        assert body["response_format"]["type"] == "json_object"

    def test_no_system_prompt(self) -> None:
        """Should work without system prompt."""
        client = self._make_client()

        mock_resp = self._mock_response({"result": "ok"})

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.generate(prompt="Test")

        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        # Only user message, no system message
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"


class TestOpenRouterLLMClientErrors:
    """Tests for error handling and retries."""

    def _make_client(self, max_retries: int = 2) -> OpenRouterLLMClient:
        """Create a client with a mocked session."""
        return OpenRouterLLMClient(
            api_key="sk-or-v1-test",
            max_retries=max_retries,
        )

    def test_auth_error_no_retry(self) -> None:
        """401 errors should not be retried."""
        client = self._make_client(max_retries=3)

        mock_resp = Mock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_resp.text = "Unauthorized"

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            response = client.generate(prompt="Test")

        assert not response.success
        assert "Invalid API key" in response.error
        # Should only be called once (no retries for auth errors)
        assert mock_post.call_count == 1
        assert client.stats["total_errors"] == 1

    def test_rate_limit_retry(self) -> None:
        """429 errors should be retried."""
        client = self._make_client(max_retries=2)

        rate_limit_resp = Mock()
        rate_limit_resp.status_code = 429
        rate_limit_resp.json.return_value = {"error": {"message": "Rate limited"}}
        rate_limit_resp.text = "Rate limited"

        success_resp = Mock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "choices": [{"message": {"content": '{"result": "ok"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "test",
        }

        with patch.object(
            client._session, "post", side_effect=[rate_limit_resp, success_resp]
        ):
            with patch("chaoswopr.agents.openrouter_client.time.sleep"):
                response = client.generate(prompt="Test")

        assert response.success
        assert response.structured == {"result": "ok"}

    def test_timeout_retry(self) -> None:
        """Timeout errors should be retried."""
        client = self._make_client(max_retries=2)

        import requests as req

        with patch.object(
            client._session,
            "post",
            side_effect=req.exceptions.Timeout("Connection timed out"),
        ):
            with patch("chaoswopr.agents.openrouter_client.time.sleep"):
                response = client.generate(prompt="Test")

        assert not response.success
        assert "timed out" in response.error

    def test_connection_error_retry(self) -> None:
        """Connection errors should be retried."""
        client = self._make_client(max_retries=2)

        import requests as req

        with patch.object(
            client._session,
            "post",
            side_effect=req.exceptions.ConnectionError("DNS resolution failed"),
        ):
            with patch("chaoswopr.agents.openrouter_client.time.sleep"):
                response = client.generate(prompt="Test")

        assert not response.success
        assert "Connection error" in response.error

    def test_empty_choices(self) -> None:
        """Should handle empty choices array."""
        client = self._make_client()

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
        }

        with patch.object(client._session, "post", return_value=mock_resp):
            response = client.generate(prompt="Test")

        assert not response.success
        assert "No choices" in response.error

    def test_malformed_json_response(self) -> None:
        """Should handle malformed JSON from the API."""
        client = self._make_client()

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        with patch.object(client._session, "post", return_value=mock_resp):
            response = client.generate(prompt="Test")

        assert not response.success
        assert "Failed to parse" in response.error


class TestOpenRouterLLMClientExtractJSON:
    """Tests for the JSON extraction method."""

    def test_direct_json(self) -> None:
        client = OpenRouterLLMClient(api_key="test")
        result = client._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_block(self) -> None:
        client = OpenRouterLLMClient(api_key="test")
        result = client._extract_json('Here is the result:\n```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_in_generic_code_block(self) -> None:
        client = OpenRouterLLMClient(api_key="test")
        result = client._extract_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self) -> None:
        client = OpenRouterLLMClient(api_key="test")
        result = client._extract_json('Some text before {"key": "value"} and after')
        assert result == {"key": "value"}

    def test_no_json(self) -> None:
        client = OpenRouterLLMClient(api_key="test")
        result = client._extract_json("This is plain text with no JSON")
        assert result is None

    def test_empty_string(self) -> None:
        client = OpenRouterLLMClient(api_key="test")
        result = client._extract_json("")
        assert result is None


class TestOpenRouterAPIError:
    """Tests for OpenRouterAPIError."""

    def test_error_creation(self) -> None:
        error = OpenRouterAPIError(
            message="Rate limited",
            status_code=429,
            retryable=True,
        )
        assert error.status_code == 429
        assert error.retryable is True
        assert "429" in str(error)
        assert "Rate limited" in str(error)

    def test_non_retryable_error(self) -> None:
        error = OpenRouterAPIError(
            message="Invalid key",
            status_code=401,
            retryable=False,
        )
        assert not error.retryable


class TestOpenRouterFromEnv:
    """Tests for the from_env class method."""

    def test_from_env_with_key(self) -> None:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-v1-test123"}):
            client = OpenRouterLLMClient.from_env()
            assert client.is_available()

    def test_from_env_without_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                OpenRouterLLMClient.from_env()

    def test_from_env_custom_model(self) -> None:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-v1-test"}):
            client = OpenRouterLLMClient.from_env(model="anthropic/claude-sonnet-4.5")
            assert client.model == "anthropic/claude-sonnet-4.5"
