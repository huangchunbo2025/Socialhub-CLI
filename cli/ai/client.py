"""AI API client — handles Azure OpenAI and OpenAI calls."""

import json
import threading
import time
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..config import load_config
from ..network import build_httpx_kwargs
from .prompt import SYSTEM_PROMPT

console = Console()

_AI_REQUEST_TIMEOUT = 60  # seconds; thread join uses +5s headroom


def get_ai_config() -> dict:
    """Get AI configuration from config file and environment variables.

    Environment variable overrides are applied by _apply_env_overrides() inside
    load_config(), so this function simply reads the already-merged config.
    Single source of truth for env overrides: cli/config.py::_apply_env_overrides().
    """
    config = load_config()
    ai_config = config.ai

    return {
        "provider": ai_config.provider,
        "azure_endpoint": ai_config.azure_endpoint,
        "azure_api_key": ai_config.azure_api_key,
        "azure_deployment": ai_config.azure_deployment,
        "azure_api_version": ai_config.azure_api_version,
        "openai_api_key": ai_config.openai_api_key,
        "openai_model": ai_config.openai_model,
    }


def _build_messages(history: Optional[list], user_msg: str) -> list[dict]:
    """Build the messages list for the AI API call."""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    return messages


def call_ai_api(
    user_message: str,
    api_key: Optional[str] = None,
    max_retries: int = 3,
    show_thinking: bool = True,
    session_history: Optional[list] = None,
) -> tuple[str, Optional[dict]]:
    """Call AI API to process natural language (supports Azure OpenAI and OpenAI).

    Args:
        user_message: The user's message to send to the AI
        api_key: Optional API key override
        max_retries: Maximum number of retry attempts for timeout errors (default: 3)
        show_thinking: Whether to show "Thinking..." with elapsed time (default: True)
        session_history: Optional list of prior conversation messages to inject for multi-turn context

    Returns:
        Tuple of (response_text, usage_dict). usage_dict contains prompt_tokens,
        completion_tokens, total_tokens (or None on error).
    """
    ai_config = get_ai_config()
    provider = ai_config["provider"]
    _net_kwargs = build_httpx_kwargs(load_config().network)

    last_error = None

    def make_api_request(provider: str, ai_config: dict, api_key: Optional[str], result_holder: dict):
        """Make the actual API request in a separate thread."""
        try:
            messages = _build_messages(session_history, user_message)
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
                body: dict = {"messages": messages, "temperature": 0.7, "max_tokens": 1000}
            else:
                key = api_key or ai_config["openai_api_key"]
                if not key:
                    result_holder["error"] = "Error: OpenAI API Key not configured. Run 'sh config set ai.openai_api_key YOUR_KEY' or set OPENAI_API_KEY environment variable."
                    return

                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                body = {"model": ai_config["openai_model"], "messages": messages, "temperature": 0.7, "max_tokens": 1000}

            with httpx.Client(timeout=_AI_REQUEST_TIMEOUT, **_net_kwargs) as client:
                response = client.post(url, headers=headers, json=body)

            result_holder["response"] = response
        except httpx.TimeoutException:
            result_holder["timeout"] = True
        except httpx.ConnectError:
            result_holder["connect_error"] = True
        except Exception as e:
            result_holder["error"] = f"Error: {type(e).__name__}: {e}"

    for attempt in range(max_retries):
        result_holder = {}
        start_time = time.time()

        api_thread = threading.Thread(
            target=make_api_request,
            args=(provider, ai_config, api_key, result_holder),
            daemon=True,  # won't block process exit on SIGINT
        )
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
            except Exception:
                console.print("[dim]Thinking...[/dim]")
            finally:
                api_thread.join(timeout=_AI_REQUEST_TIMEOUT + 5)
        else:
            api_thread.join(timeout=_AI_REQUEST_TIMEOUT + 5)
        elapsed_time = time.time() - start_time

        if api_thread.is_alive():
            result_holder["timeout"] = True

        if "error" in result_holder:
            return result_holder["error"], None

        if "timeout" in result_holder:
            last_error = "API request timeout"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                console.print(f"[yellow]API request timeout, retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            continue

        if "connect_error" in result_holder:
            last_error = "Network connection failed"
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                console.print(f"[yellow]Network connection failed, retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            continue

        if "response" in result_holder:
            response = result_holder["response"]
            if response.status_code in (429, 503):
                last_error = f"API rate-limited or unavailable ({response.status_code})"
                if attempt < max_retries - 1:
                    try:
                        retry_after = int(response.headers.get("Retry-After", (attempt + 1) * 2))
                    except (ValueError, TypeError):
                        retry_after = (attempt + 1) * 2
                    wait_time = min(retry_after, 30)
                    console.print(f"[yellow]API rate-limited ({response.status_code}), retrying in {wait_time}s ({attempt + 1}/{max_retries})...[/yellow]")
                    time.sleep(wait_time)
                continue
            if response.status_code != 200:
                try:
                    err_msg = response.json().get("error", {}).get("message", "") or response.text[:200]
                except Exception:
                    err_msg = response.text[:200]
                return f"API Error: {response.status_code} - {err_msg}", None

            try:
                result = response.json()
                console.print(f"[dim]Completed in {elapsed_time:.1f}s[/dim]")
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage")  # {"prompt_tokens": N, "completion_tokens": M, "total_tokens": K}
                return content, usage
            except (KeyError, json.JSONDecodeError) as e:
                return f"Error parsing API response: {e}", None

    return f"Error: {last_error or 'Unknown error'}, retried {max_retries} times.", None
