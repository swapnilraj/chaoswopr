"""OpenRouter LLM client for chaoswopr agent system.

Provides an LLM client that calls the OpenRouter API (https://openrouter.ai),
which offers a unified interface to multiple LLM providers including Anthropic
Claude, OpenAI GPT, and others.

The client supports:
  - Structured JSON output via response_format
  - Exponential backoff with retries
  - Configurable model selection per use case
  - Token usage tracking
  - Timeout handling

OpenRouter API is OpenAI-compatible:
  POST https://openrouter.ai/api/v1/chat/completions
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from chaoswopr.agents.llm_client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

# Default models for different use cases
DEFAULT_HYPOTHESIS_MODEL = "anthropic/claude-opus-4"
DEFAULT_RCA_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterLLMClient(LLMClient):
    """LLM client using the OpenRouter API.

    OpenRouter provides a unified, OpenAI-compatible API for accessing
    multiple LLM providers. This client handles authentication, retries,
    structured output parsing, and error handling.

    Examples:
        >>> client = OpenRouterLLMClient(api_key="sk-or-v1-...")  # doctest: +SKIP
        >>> response = client.generate(
        ...     prompt="Generate a hypothesis",
        ...     system_prompt="You are an expert...",
        ...     json_schema={"type": "object", "properties": {...}},
        ... )  # doctest: +SKIP
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_HYPOTHESIS_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        http_referer: str = "https://github.com/chaoswopr/chaoswopr",
        app_title: str = "chaoswopr",
    ) -> None:
        """Initialize the OpenRouter client.

        Args:
            api_key: OpenRouter API key (starts with sk-or-v1-...).
            model: Default model identifier.
            base_url: OpenRouter API base URL.
            timeout_seconds: Request timeout in seconds.
            max_retries: Maximum number of retries on failure.
            http_referer: HTTP-Referer header for OpenRouter tracking.
            app_title: X-Title header for OpenRouter dashboard.
        """
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._http_referer = http_referer
        self._app_title = app_title

        # Session for connection pooling
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": http_referer,
            "X-Title": app_title,
            "Content-Type": "application/json",
        })

        # Stats
        self._total_calls = 0
        self._total_tokens = 0
        self._total_errors = 0

        logger.info(
            "OpenRouter client initialized (model=%s, base_url=%s)",
            model,
            base_url,
        )

    @classmethod
    def from_env(cls, model: str | None = None) -> OpenRouterLLMClient:
        """Create an OpenRouter client from environment variables.

        Reads OPENROUTER_API_KEY from the environment.

        Args:
            model: Override default model.

        Returns:
            Configured OpenRouterLLMClient.

        Raises:
            ValueError: If OPENROUTER_API_KEY is not set.
        """
        import os

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is not set. "
                "Get your key at https://openrouter.ai"
            )

        return cls(
            api_key=api_key,
            model=model or os.getenv("CHAOSWOPR_DEFAULT_MODEL", DEFAULT_HYPOTHESIS_MODEL),
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
            timeout_seconds=int(os.getenv("OPENROUTER_TIMEOUT", "60")),
            max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "3")),
        )

    @property
    def model(self) -> str:
        """Get the default model identifier."""
        return self._model

    @property
    def stats(self) -> dict[str, int]:
        """Get client usage statistics."""
        return {
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "total_errors": self._total_errors,
        }

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate a response using the OpenRouter API.

        Sends a chat completion request and returns structured output.
        Includes retry logic with exponential backoff for transient failures.

        Args:
            prompt: User prompt content.
            system_prompt: System prompt for context and persona.
            json_schema: Expected JSON output schema (appended to prompt).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0.0-1.0).
            model: Override the default model for this call.

        Returns:
            LLMResponse with content and structured data.
        """
        use_model = model or self._model

        # Build messages
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # If JSON schema is provided, append instructions to the prompt
        full_prompt = prompt
        if json_schema:
            schema_str = json.dumps(json_schema, indent=2)
            full_prompt += (
                "\n\nYou MUST respond with valid JSON matching this schema exactly. "
                "Do not include any text before or after the JSON.\n"
                f"```json\n{schema_str}\n```"
            )

        messages.append({"role": "user", "content": full_prompt})

        # Build request body
        body: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Request JSON output format when schema is provided
        if json_schema:
            body["response_format"] = {"type": "json_object"}

        # Execute with retries
        last_error: str | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._make_request(body)
                self._total_calls += 1

                # Parse response
                return self._parse_response(response, use_model)

            except requests.exceptions.Timeout:
                last_error = f"Request timed out after {self._timeout_seconds}s"
                logger.warning(
                    "OpenRouter request timed out (attempt %d/%d)",
                    attempt + 1,
                    self._max_retries,
                )
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
                logger.warning(
                    "OpenRouter connection error (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries,
                    e,
                )
            except OpenRouterAPIError as e:
                last_error = str(e)
                if not e.retryable:
                    # Non-retryable errors (auth, bad request) fail immediately
                    logger.error("OpenRouter API error (non-retryable): %s", e)
                    break
                logger.warning(
                    "OpenRouter API error (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries,
                    e,
                )
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error("Unexpected error calling OpenRouter: %s", e)
                break

            # Exponential backoff before retry
            if attempt < self._max_retries - 1:
                wait_time = 2 ** attempt
                logger.debug("Retrying in %ds...", wait_time)
                time.sleep(wait_time)

        # All retries exhausted
        self._total_errors += 1
        return LLMResponse(
            success=False,
            error=last_error or "Unknown error",
            model=use_model,
        )

    def is_available(self) -> bool:
        """Check if the OpenRouter client is available and configured.

        Verifies that the API key is set. Does not make a network call.
        """
        return bool(self._api_key)

    def _make_request(self, body: dict[str, Any]) -> requests.Response:
        """Make an HTTP request to the OpenRouter API.

        Args:
            body: Request body dictionary.

        Returns:
            HTTP response.

        Raises:
            OpenRouterAPIError: If the API returns an error status.
            requests.exceptions.Timeout: If the request times out.
            requests.exceptions.ConnectionError: If connection fails.
        """
        url = f"{self._base_url}/chat/completions"

        response = self._session.post(
            url,
            json=body,
            timeout=self._timeout_seconds,
        )

        if response.status_code != 200:
            # Parse error response
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text)
            except (json.JSONDecodeError, ValueError):
                error_msg = response.text

            retryable = response.status_code in (429, 500, 502, 503, 504)
            raise OpenRouterAPIError(
                message=error_msg,
                status_code=response.status_code,
                retryable=retryable,
            )

        return response

    def _parse_response(
        self,
        response: requests.Response,
        model: str,
    ) -> LLMResponse:
        """Parse an OpenRouter API response.

        Args:
            response: HTTP response from the API.
            model: Model that was used.

        Returns:
            Parsed LLMResponse.
        """
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            return LLMResponse(
                success=False,
                error=f"Failed to parse API response: {e}",
                model=model,
            )

        # Extract content from choices
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(
                success=False,
                error="No choices in API response",
                model=model,
            )

        content = choices[0].get("message", {}).get("content", "")

        # Extract usage stats
        usage_data = data.get("usage", {})
        usage = {
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }
        self._total_tokens += usage.get("total_tokens", 0)

        # Actual model used (may differ from requested)
        actual_model = data.get("model", model)

        # Try to parse content as JSON
        structured = self._extract_json(content)

        return LLMResponse(
            content=content,
            structured=structured,
            model=actual_model,
            usage=usage,
            success=True,
        )

    def _extract_json(self, content: str) -> dict[str, Any] | None:
        """Extract JSON from LLM response content.

        Handles raw JSON, markdown code blocks, and mixed content.

        Args:
            content: Raw response content.

        Returns:
            Parsed JSON dictionary, or None if not parseable.
        """
        if not content:
            return None

        # Try direct JSON parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        json_content = content
        if "```json" in json_content:
            try:
                json_content = json_content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_content)
            except (json.JSONDecodeError, IndexError):
                pass
        elif "```" in json_content:
            try:
                json_content = json_content.split("```")[1].split("```")[0].strip()
                return json.loads(json_content)
            except (json.JSONDecodeError, IndexError):
                pass

        # Try to find JSON object in the content
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            return json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        logger.debug("Could not extract JSON from LLM response")
        return None


class OpenRouterAPIError(Exception):
    """Error from the OpenRouter API.

    Attributes:
        message: Error message.
        status_code: HTTP status code.
        retryable: Whether this error is retryable.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        retryable: bool = False,
    ) -> None:
        """Initialize the error.

        Args:
            message: Error message.
            status_code: HTTP status code.
            retryable: Whether this error is retryable.
        """
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable

    def __str__(self) -> str:
        """Format the error message."""
        return f"OpenRouter API error (status={self.status_code}): {super().__str__()}"
