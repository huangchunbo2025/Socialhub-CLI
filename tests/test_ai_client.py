"""Tests for cli.ai.client — call_ai_api and get_ai_config."""

import time
from unittest.mock import MagicMock, patch, call

import httpx
import pytest

from cli.ai.client import call_ai_api, get_ai_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(status_code: int, json_body: dict = None, headers: dict = None) -> MagicMock:
    """Return a mock httpx.Response with the given status code and optional JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.return_value = {}
    resp.text = ""
    return resp


def _ok_response() -> MagicMock:
    """200 OK with a minimal valid OpenAI-style chat completion body."""
    return _make_mock_response(200, {
        "choices": [{"message": {"content": "Hello from AI"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


# ---------------------------------------------------------------------------
# get_ai_config
# ---------------------------------------------------------------------------

class TestGetAiConfig:
    def test_reads_from_merged_config(self):
        """get_ai_config() must delegate to load_config(), not raw env vars."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(
            provider="openai",
            openai_api_key="sk-test-key",
            openai_model="gpt-4",
        )

        with patch("cli.ai.client.load_config", return_value=mock_config) as mock_load:
            result = get_ai_config()

        mock_load.assert_called_once()
        assert result["provider"] == "openai"
        assert result["openai_api_key"] == "sk-test-key"
        assert result["openai_model"] == "gpt-4"

    def test_returns_required_keys(self):
        """get_ai_config() must always return the full set of expected keys."""
        from cli.config import Config

        with patch("cli.ai.client.load_config", return_value=Config()):
            result = get_ai_config()

        required_keys = {
            "provider",
            "azure_endpoint",
            "azure_api_key",
            "azure_deployment",
            "azure_api_version",
            "openai_api_key",
            "openai_model",
        }
        assert required_keys.issubset(result.keys())

    def test_azure_defaults(self):
        """Default config produces azure provider."""
        from cli.config import Config

        with patch("cli.ai.client.load_config", return_value=Config()):
            result = get_ai_config()

        assert result["provider"] == "azure"


# ---------------------------------------------------------------------------
# call_ai_api — HTTP 429 retry
# ---------------------------------------------------------------------------

class TestCallAiApiRetry429:
    def test_retries_on_429_and_succeeds(self):
        """call_ai_api should retry on 429 and eventually return the successful response."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        responses = [
            _make_mock_response(429, headers={"Retry-After": "0"}),
            _make_mock_response(429, headers={"Retry-After": "0"}),
            _ok_response(),
        ]
        response_iter = iter(responses)

        def _fake_post(url, headers=None, json=None, **kwargs):
            return next(response_iter)

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep") as mock_sleep:

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_http_client

            text, usage = call_ai_api(
                "hello",
                max_retries=3,
                show_thinking=False,
            )

        assert text == "Hello from AI"
        assert usage is not None
        # sleep must have been called at least once (for the 429 backoff)
        assert mock_sleep.call_count >= 1

    def test_sleep_called_on_429(self):
        """time.sleep must be invoked when a 429 is encountered and retries remain."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        responses = [
            _make_mock_response(429, headers={"Retry-After": "0"}),
            _ok_response(),
        ]
        response_iter = iter(responses)

        def _fake_post(url, **kwargs):
            return next(response_iter)

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep") as mock_sleep:

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_http_client

            call_ai_api("hello", max_retries=3, show_thinking=False)

        mock_sleep.assert_called()


# ---------------------------------------------------------------------------
# call_ai_api — HTTP 503 retry
# ---------------------------------------------------------------------------

class TestCallAiApiRetry503:
    def test_retries_on_503_and_succeeds(self):
        """call_ai_api should retry on 503 and eventually return the successful response."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        responses = [
            _make_mock_response(503, headers={}),
            _make_mock_response(503, headers={}),
            _ok_response(),
        ]
        response_iter = iter(responses)

        def _fake_post(url, **kwargs):
            return next(response_iter)

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep"):

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_http_client

            text, usage = call_ai_api("hello", max_retries=3, show_thinking=False)

        assert text == "Hello from AI"

    def test_sleep_called_on_503(self):
        """time.sleep must be invoked when a 503 is encountered and retries remain."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        responses = [
            _make_mock_response(503, headers={}),
            _ok_response(),
        ]
        response_iter = iter(responses)

        def _fake_post(url, **kwargs):
            return next(response_iter)

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep") as mock_sleep:

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_http_client

            call_ai_api("hello", max_retries=3, show_thinking=False)

        mock_sleep.assert_called()


# ---------------------------------------------------------------------------
# call_ai_api — exhausted retries
# ---------------------------------------------------------------------------

class TestCallAiApiExhaustedRetries:
    def test_returns_error_string_after_exhausting_retries_429(self):
        """call_ai_api returns an error string when all retries are consumed on 429."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        def _always_429(url, **kwargs):
            return _make_mock_response(429, headers={"Retry-After": "0"})

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep"):

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _always_429
            mock_client_cls.return_value = mock_http_client

            text, usage = call_ai_api("hello", max_retries=3, show_thinking=False)

        assert isinstance(text, str)
        assert "Error" in text or "error" in text.lower() or "retried" in text
        assert usage is None

    def test_returns_error_string_after_exhausting_retries_503(self):
        """call_ai_api returns an error string when all retries are consumed on 503."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        def _always_503(url, **kwargs):
            return _make_mock_response(503, headers={})

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep"):

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _always_503
            mock_client_cls.return_value = mock_http_client

            text, usage = call_ai_api("hello", max_retries=3, show_thinking=False)

        assert isinstance(text, str)
        assert "Error" in text or "retried" in text
        assert usage is None

    def test_max_retries_respected(self):
        """The function must make exactly max_retries POST calls when all fail with 429."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        call_count = {"n": 0}

        def _always_429(url, **kwargs):
            call_count["n"] += 1
            return _make_mock_response(429, headers={"Retry-After": "0"})

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep"):

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _always_429
            mock_client_cls.return_value = mock_http_client

            call_ai_api("hello", max_retries=3, show_thinking=False)

        assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# call_ai_api — Retry-After header edge cases
# ---------------------------------------------------------------------------


class TestRetryAfterHeaderParsing:
    def test_non_integer_retry_after_does_not_crash(self):
        """An HTTP-date Retry-After value (non-integer) must not raise ValueError.

        Azure API Gateway sometimes returns Retry-After as an RFC 7231 date string
        (e.g. "Wed, 01 Jan 2026 12:00:00 GMT"). int() on such a string raises
        ValueError; the retry logic must fall back gracefully.
        """
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        responses = [
            _make_mock_response(429, headers={"Retry-After": "Wed, 01 Jan 2026 12:00:00 GMT"}),
            _ok_response(),
        ]
        response_iter = iter(responses)

        def _fake_post(url, **kwargs):
            return next(response_iter)

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep"):

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_http_client

            text, usage = call_ai_api("hello", max_retries=3, show_thinking=False)

        assert text == "Hello from AI"

    def test_missing_retry_after_header_uses_backoff(self):
        """When Retry-After header is absent, exponential backoff is used."""
        from cli.config import Config, AIConfig

        mock_config = Config()
        mock_config.ai = AIConfig(provider="openai", openai_api_key="sk-test")

        responses = [
            _make_mock_response(429, headers={}),
            _ok_response(),
        ]
        response_iter = iter(responses)

        sleep_calls = []

        def _fake_post(url, **kwargs):
            return next(response_iter)

        with patch("cli.ai.client.load_config", return_value=mock_config), \
             patch("cli.ai.client.build_httpx_kwargs", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("cli.ai.client.time.sleep", side_effect=lambda s: sleep_calls.append(s)):

            mock_http_client = MagicMock()
            mock_http_client.__enter__ = lambda s: s
            mock_http_client.__exit__ = MagicMock(return_value=False)
            mock_http_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_http_client

            text, usage = call_ai_api("hello", max_retries=3, show_thinking=False)

        assert text == "Hello from AI"
        assert len(sleep_calls) == 1
        assert sleep_calls[0] <= 30
