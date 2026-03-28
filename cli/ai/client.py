"""AI API client — handles Azure OpenAI and OpenAI calls."""

import json
import os
import threading
import time
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..config import load_config
from .prompt import SYSTEM_PROMPT

console = Console()


def get_ai_config() -> dict:
    """Get AI configuration from config file or environment."""
    config = load_config()
    ai_config = config.ai

    return {
        "provider": os.getenv("AI_PROVIDER", ai_config.provider),
        "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ai_config.azure_endpoint),
        "azure_api_key": os.getenv("AZURE_OPENAI_API_KEY", ai_config.azure_api_key),
        "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", ai_config.azure_deployment),
        "azure_api_version": os.getenv("AZURE_OPENAI_API_VERSION", ai_config.azure_api_version),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ai_config.openai_api_key),
        "openai_model": os.getenv("OPENAI_MODEL", ai_config.openai_model),
    }


def call_ai_api(user_message: str, api_key: Optional[str] = None, max_retries: int = 3, show_thinking: bool = True) -> str:
    """Call AI API to process natural language (supports Azure OpenAI and OpenAI).

    Args:
        user_message: The user's message to send to the AI
        api_key: Optional API key override
        max_retries: Maximum number of retry attempts for timeout errors (default: 3)
        show_thinking: Whether to show "Thinking..." with elapsed time (default: True)
    """
    ai_config = get_ai_config()
    provider = ai_config["provider"]

    last_error = None

    def make_api_request(provider: str, ai_config: dict, api_key: Optional[str], result_holder: dict):
        """Make the actual API request in a separate thread."""
        try:
            if provider == "azure":
                key = api_key or ai_config["azure_api_key"]
                if not key:
                    result_holder["error"] = "Error: Azure OpenAI API Key not configured. Run 'sh config set ai.azure_api_key YOUR_KEY' or set AZURE_OPENAI_API_KEY environment variable."
                    return

                endpoint = ai_config["azure_endpoint"]
                deployment = ai_config["azure_deployment"]
                api_version = ai_config["azure_api_version"]
                url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

                response = httpx.post(
                    url,
                    headers={
                        "api-key": key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000,
                    },
                    timeout=60,
                )
            else:
                key = api_key or ai_config["openai_api_key"]
                if not key:
                    result_holder["error"] = "Error: OpenAI API Key not configured. Run 'sh config set ai.openai_api_key YOUR_KEY' or set OPENAI_API_KEY environment variable."
                    return

                response = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": ai_config["openai_model"],
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000,
                    },
                    timeout=60,
                )

            result_holder["response"] = response
        except httpx.TimeoutException:
            result_holder["timeout"] = True
        except httpx.ConnectError:
            result_holder["connect_error"] = True
        except Exception as e:
            result_holder["error"] = f"Error: {str(e)}"

    for attempt in range(max_retries):
        result_holder = {}
        start_time = time.time()

        api_thread = threading.Thread(
            target=make_api_request,
            args=(provider, ai_config, api_key, result_holder)
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
                api_thread.join()
        else:
            api_thread.join()
        elapsed_time = time.time() - start_time

        if "error" in result_holder:
            return result_holder["error"]

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
            if response.status_code != 200:
                return f"API Error: {response.status_code} - {response.text}"

            try:
                result = response.json()
                console.print(f"[dim]Completed in {elapsed_time:.1f}s[/dim]")
                return result["choices"][0]["message"]["content"]
            except (KeyError, json.JSONDecodeError) as e:
                return f"Error parsing API response: {e}"

    return f"Error: {last_error or 'Unknown error'}, retried {max_retries} times."
