"""AI insights generator — summarizes plan results."""

import logging as _logging

from .client import call_ai_api

_logger = _logging.getLogger(__name__)


def generate_insights(
    query: str,
    results: list[dict],
    session_id: str = "",
    trace_id: str = "",
    no_memory: bool = False,
    trace_logger=None,
    memory_manager=None,
) -> str:
    """Generate AI insights based on query results.

    Args:
        query: The original user query
        results: List of step execution results
        session_id: Current session ID (for memory audit linking)
        trace_id: Current trace ID (for memory audit linking)
        no_memory: If True, skip memory write hook
        memory_manager: Existing MemoryManager to reuse; if None a fresh one is created.

    Returns:
        Insights text (empty string if no results or API error)
    """
    results_text = ""
    for r in results:
        if r["success"] and r["output"]:
            results_text += f"\n### {r['description']}\n```\n{r['output'][:2000]}\n```\n"

    if not results_text:
        return ""

    insight_prompt = f"""User query: {query}

The following are the data results from the analysis:
{results_text}

Please provide concise insight analysis based on the above data:
1. Key findings (2-3 points)
2. Trend analysis
3. Business recommendations (1-2 actionable suggestions)

Output insights directly, no commands. Be concise and professional."""

    text, insight_usage = call_ai_api(insight_prompt, show_thinking=False)
    _logger.debug("insights usage: %s", insight_usage)

    # Memory hook — persist this insight for future sessions.
    # Reuse the caller's MemoryManager instance when provided to avoid a redundant
    # cold-load of all memory layers.
    if text and not text.startswith("Error:") and not no_memory:
        try:
            if memory_manager is None:
                from ..memory import MemoryManager
                memory_manager = MemoryManager(trace_logger=trace_logger)
            mm = memory_manager
            mm.save_insight_from_ai(
                raw_content=text,
                topic=query[:80],
                tags=["analysis"],
                session_id=session_id,
                trace_id=trace_id,
                no_memory=no_memory,
            )
        except Exception as _mem_err:
            _logger.debug("Memory write skipped (non-fatal): %s", _mem_err)

    return text
