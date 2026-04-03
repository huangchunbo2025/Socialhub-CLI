"""SessionExtractor — extract structured memory from a completed conversation.

Calls the AI API once at session end to distill reusable facts.
Uses a daemon thread + timeout so the main CLI flow is never blocked.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

from .models import ExtractionResult, InsightData, UserPreferencesUpdate

if TYPE_CHECKING:
    from ..ai.session import Session

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are a memory extraction assistant. Analyze the conversation below and extract \
information worth remembering for future sessions.

IMPORTANT RULES:
- Only extract CLEARLY STATED preferences or conclusions — never infer or guess.
- business_insights must be factual conclusions from actual data analysis, NOT plans or suggestions.
- If nothing is worth saving, set nothing_to_save: true.
- Keep session_summary under 80 characters.
- Do NOT include customer names, phone numbers, emails, or order IDs in any field.

Output ONLY valid JSON matching this schema:
{
  "nothing_to_save": false,
  "user_preferences_update": {
    "default_period": null,
    "preferred_dimensions": null,
    "key_metrics": null,
    "rfm_focus": null,
    "output_format": null,
    "show_yoy": null
  },
  "business_insights": [
    {
      "topic": "...",
      "conclusion": "...",
      "tags": ["..."],
      "data_period": "",
      "confidence": "high|medium|low"
    }
  ],
  "session_summary": "..."
}

CONVERSATION:
{conversation}
"""


class SessionExtractor:
    """Extract structured memory from a completed session using one LLM call."""

    def __init__(self, timeout_s: int = 30, ai_caller=None) -> None:
        """
        Args:
            timeout_s: Max seconds to wait for LLM extraction (default 30).
            ai_caller: Optional injectable for testing. If None, uses call_ai_api.
        """
        self._timeout_s = timeout_s
        self._ai_caller = ai_caller

    def extract(self, session: Session) -> ExtractionResult:
        """Run extraction in a daemon thread with timeout.

        Returns ExtractionResult. On timeout or error, returns skipped=True.
        Never raises.
        """
        messages = session.get_history()
        if not messages:
            return ExtractionResult(skipped=True, skip_reason="empty_session")

        # Build conversation text
        conv_lines = []
        for m in messages[-20:]:  # cap at last 20 messages to stay within token limits
            role = m.get("role", "")
            content = m.get("content", "")[:500]  # truncate long messages
            conv_lines.append(f"{role.upper()}: {content}")
        conversation = "\n".join(conv_lines)

        result_holder: dict = {}
        done_event = threading.Event()

        def _run() -> None:
            try:
                # Use replace() instead of format() to avoid KeyError when
                # conversation text contains literal {placeholder} syntax.
                prompt = _EXTRACTION_PROMPT.replace("{conversation}", conversation)
                caller = self._ai_caller or _default_ai_caller()
                response, _ = caller(prompt, show_thinking=False)
                result_holder["response"] = response
            except Exception as exc:
                result_holder["error"] = str(exc)
            finally:
                done_event.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        finished = done_event.wait(timeout=self._timeout_s)

        if not finished:
            return ExtractionResult(skipped=True, skip_reason="extractor_timeout")

        if "error" in result_holder:
            logger.debug("Memory extractor error: %s", result_holder["error"])
            return ExtractionResult(skipped=True, skip_reason="extractor_error")

        return _parse_extraction_response(result_holder.get("response", ""))


def _default_ai_caller():
    from ..ai.client import call_ai_api
    return call_ai_api


def _parse_extraction_response(response: str) -> ExtractionResult:
    """Parse LLM JSON response into ExtractionResult. Never raises."""
    try:
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = json.loads(text)

        if data.get("nothing_to_save"):
            return ExtractionResult(nothing_to_save=True)

        prefs = data.get("user_preferences_update") or {}
        insights_raw = data.get("business_insights") or []
        summary = (data.get("session_summary") or "")[:100]

        parsed_insights = []
        for raw in insights_raw:
            if isinstance(raw, dict) and raw.get("topic") and raw.get("conclusion"):
                parsed_insights.append(
                    InsightData(
                        topic=str(raw["topic"])[:100],
                        conclusion=str(raw["conclusion"])[:500],
                        tags=[str(t) for t in (raw.get("tags") or [])[:5]],
                        data_period=str(raw.get("data_period") or "")[:50],
                        confidence=str(raw.get("confidence") or "medium"),
                    )
                )

        return ExtractionResult(
            user_preferences_update=UserPreferencesUpdate(**{
                k: v for k, v in prefs.items() if v is not None
            }) if prefs else UserPreferencesUpdate(),
            business_insights=parsed_insights,
            session_summary=summary,
        )
    except Exception as exc:
        logger.debug("Memory extraction parse failed: %s", exc)
        return ExtractionResult(skipped=True, skip_reason="parse_error")
