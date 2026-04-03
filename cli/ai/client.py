"""AI API client — handles Azure OpenAI and OpenAI calls."""

import json
import logging
import threading
import time

import httpx
from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..config import load_config
from ..network import build_httpx_kwargs
from .prompt import SYSTEM_PROMPT

console = Console()
logger = logging.getLogger(__name__)

_AI_REQUEST_TIMEOUT = 60  # seconds; thread join uses +5s headroom


def get_ai_config(config=None) -> dict:
    """Return AI config as a plain dict.

    Pass a pre-loaded config to avoid a redundant load_config() call (e.g. when
    the caller also needs network config).  Omit to let this function load it.
    """
    if config is None:
        config = load_config()
    ai = config.ai
    return {
        "provider": ai.provider,
        "azure_endpoint": ai.azure_endpoint,
        "azure_api_key": ai.azure_api_key,
        "azure_deployment": ai.azure_deployment,
        "azure_api_version": ai.azure_api_version,
        "openai_api_key": ai.openai_api_key,
        "openai_model": ai.openai_model,
        "max_tokens": ai.max_tokens,
        "temperature": ai.temperature,
        "ai_timeout_s": ai.ai_timeout_s,
    }


def _build_messages(
    history: list | None,
    user_msg: str,
    system_prompt: str | None = None,  # None → falls back to static SYSTEM_PROMPT
) -> list[dict]:
    """Build the messages list for the AI API call."""
    effective_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    messages: list[dict] = [{"role": "system", "content": effective_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    return messages


def call_ai_api(
    user_message: str,
    api_key: str | None = None,
    max_retries: int = 3,
    show_thinking: bool = True,
    session_history: list | None = None,
    system_prompt: str | None = None,
) -> tuple[str, dict | None]:
    """Call AI API to process natural language (supports Azure OpenAI and OpenAI).

    Args:
        user_message: The user's message to send to the AI
        api_key: Optional API key override
        max_retries: Maximum number of retry attempts for timeout errors (default: 3)
        show_thinking: Whether to show "Thinking..." with elapsed time (default: True)
        session_history: Optional list of prior conversation messages to inject for multi-turn context
        system_prompt: Optional pre-built system prompt string. Build via
                       MemoryManager.build_system_prompt() before calling.
                       Pass None to use the static BASE_SYSTEM_PROMPT (backward-compatible default).

    Returns:
        Tuple of (response_text, usage_dict). usage_dict contains prompt_tokens,
        completion_tokens, total_tokens (or None on error).
    """
    _loaded_config = load_config()
    ai_config = get_ai_config(_loaded_config)
    provider = ai_config["provider"]
    _timeout = ai_config.get("ai_timeout_s", 60)
    _net_kwargs = build_httpx_kwargs(_loaded_config.network)

    last_error = None
    _prev_thread: threading.Thread | None = None

    def make_api_request(provider: str, ai_config: dict, api_key: str | None, result_holder: dict):
        """Make the actual API request in a separate thread."""
        try:
            messages = _build_messages(session_history, user_message, system_prompt)
            if provider == "azure":
                key = api_key or ai_config["azure_api_key"]
                if not key:
                    result_holder["error"] = "Error: Azure OpenAI API Key not configured. Run 'sh config set ai.azure_api_key YOUR_KEY' or set AZURE_OPENAI_API_KEY environment variable."
                    return

                endpoint = ai_config["azure_endpoint"]
                deployment = ai_config["azure_deployment"]
                api_version = ai_config["azure_api_version"]
                url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
                headers = {"api-key": key, "Content-Type": "application/json"}
                body: dict = {"messages": messages, "temperature": ai_config.get("temperature", 0.7), "max_tokens": ai_config.get("max_tokens", 1000)}
            else:
                key = api_key or ai_config["openai_api_key"]
                if not key:
                    result_holder["error"] = "Error: OpenAI API Key not configured. Run 'sh config set ai.openai_api_key YOUR_KEY' or set OPENAI_API_KEY environment variable."
                    return

                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                body = {
                    "model": ai_config["openai_model"],
                    "messages": messages,
                    "temperature": ai_config.get("temperature", 0.7),
                    "max_tokens": ai_config.get("max_tokens", 1000),
                }

            with httpx.Client(timeout=_timeout, **_net_kwargs) as client:
                response = client.post(url, headers=headers, json=body)

            result_holder["response"] = response
        except httpx.TimeoutException:
            result_holder["timeout"] = True
        except httpx.ConnectError:
            result_holder["connect_error"] = True
        except Exception as e:
            logger.debug("AI request exception: %s: %s", type(e).__name__, e)
            result_holder["error"] = f"Error: {type(e).__name__} (see debug log)"

    for attempt in range(max_retries):
        # Wait briefly for any previous attempt's thread before creating a new one.
        # httpx respects its timeout in normal operation, so this join usually
        # completes immediately.  The extra wait prevents multiple concurrent
        # abandoned threads when the underlying network stack is unresponsive.
        if _prev_thread is not None and _prev_thread.is_alive():
            _prev_thread.join(timeout=2)

        result_holder = {}
        start_time = time.time()

        api_thread = threading.Thread(
            target=make_api_request,
            args=(provider, ai_config, api_key, result_holder),
            daemon=True,  # won't block process exit on SIGINT
        )
        _prev_thread = api_thread
        api_thread.start()

        if show_thinking:
            spinner_chars = ["|", "/", "-", "\\"]
            spinner_idx = 0

            try:
                with Live(console=console, refresh_per_second=4, transient=True) as live:
                    while api_thread.is_alive():
                        elapsed = time.time() - start_time
                        spinner = spinner_chars[spinner_idx % len(spinner_chars)]
                        text = Text()
                        text.append(f" {spinner} ", style="cyan")
                        text.append("Thinking", style="cyan bold")
                        text.append(f" ({elapsed:.1f}s)", style="dim")
                        live.update(text)
                        spinner_idx += 1
                        time.sleep(0.25)
            except Exception as _live_err:
                logger.debug("Spinner display failed (non-fatal): %s", _live_err)
                console.print("[dim]Thinking...[/dim]")
            finally:
                api_thread.join(timeout=_timeout + 5)
        else:
            api_thread.join(timeout=_timeout + 5)
        elapsed_time = time.time() - start_time

        if api_thread.is_alive():
            result_holder["timeout"] = True
            logger.debug(
                "API thread still alive after join timeout (attempt %d/%d); "
                "daemon thread will be abandoned on retry",
                attempt + 1, max_retries,
            )

        if "error" in result_holder:
            return result_holder["error"], None

        _backoff_s = (attempt + 1) * 2

        if "timeout" in result_holder:
            last_error = "API request timeout"
            if attempt < max_retries - 1:
                console.print(f"[yellow]API request timeout, retrying in {_backoff_s}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(_backoff_s)
            continue

        if "connect_error" in result_holder:
            last_error = "Network connection failed"
            if attempt < max_retries - 1:
                console.print(f"[yellow]Network connection failed, retrying in {_backoff_s}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(_backoff_s)
            continue

        if "response" in result_holder:
            response = result_holder["response"]
            if response.status_code in (429, 503):
                last_error = f"API rate-limited or unavailable ({response.status_code})"
                if attempt < max_retries - 1:
                    try:
                        retry_after = int(response.headers.get("Retry-After", _backoff_s))
                    except (ValueError, TypeError):
                        retry_after = _backoff_s
                    wait_time = min(retry_after, 30)
                    console.print(f"[yellow]API rate-limited ({response.status_code}), retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                    time.sleep(wait_time)
                continue
            if response.status_code != 200:
                try:
                    err_msg = response.json().get("error", {}).get("message", "")
                except Exception:
                    err_msg = ""
                logger.debug("API error response body: %s", response.text[:500])
                return f"API Error: {response.status_code}" + (f" - {err_msg}" if err_msg else ""), None

            try:
                result = response.json()
                console.print(f"[dim]Completed in {elapsed_time:.1f}s[/dim]")
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage")  # {"prompt_tokens": N, "completion_tokens": M, "total_tokens": K}
                return content, usage
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                return f"Error parsing API response: {e}", None

    return f"Error: {last_error or 'Unknown error'}, retried {max_retries} times.", None
