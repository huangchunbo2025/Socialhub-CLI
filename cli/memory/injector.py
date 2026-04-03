"""SYSTEM_PROMPT dynamic builder with tiktoken token-budget control.

Layers injected in order of priority (highest = last to be cut):
  L4  user_profile    — permanent, ~300-500 tokens
  L4  business_context — permanent, ~200-400 tokens
  L2  session summaries — recent N, ~300-600 tokens
  L3  analysis insights — recent N, ~500-1500 tokens

Cutting order when over budget: L3 first → L2 → L4 (L4 never cut if possible).

This module is pure computation (no IO) and must complete in ≤ 50ms.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .models import MemoryContext

logger = logging.getLogger(__name__)

# Fallback chars-per-token ratio when tiktoken is unavailable
_CHARS_PER_TOKEN = 4

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")  # gpt-4o / gpt-3.5 encoding

    def _count_tokens(text: str) -> int:
        return len(_ENCODING.encode(text))

except ImportError:  # pragma: no cover
    logger.debug("tiktoken not installed; using char-based token estimate (1 token ≈ 4 chars)")

    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // _CHARS_PER_TOKEN)


def build_system_prompt(
    context: MemoryContext,
    base_prompt: str,
    max_tokens: int = 4000,
    inject_recent_insights: int = 5,
    inject_recent_summaries: int = 3,
    on_inject: Callable[[list[str], int, list[str], list[str]], None] | None = None,
) -> str:
    """Assemble the final SYSTEM_PROMPT with memory context injected.

    Args:
        context: MemoryContext assembled by MemoryManager.load()
        base_prompt: BASE_SYSTEM_PROMPT from cli/ai/prompt.py
        max_tokens: Maximum tokens to spend on injected memory (default 4000)
        inject_recent_insights: Max L3 insights to include
        inject_recent_summaries: Max L2 summaries to include
        on_inject: Optional callback(injected_layers, token_count, insight_ids, summary_ids)
                   used by MemoryManager to write audit log (keeps injector pure)

    Returns:
        Final SYSTEM_PROMPT string ready for AI API call.
    """
    if context.is_empty:
        if on_inject:
            on_inject([], 0, [], [])
        return base_prompt

    blocks: list[str] = []
    injected_layers: list[str] = []
    injected_insight_ids: list[str] = []
    injected_summary_ids: list[str] = []

    # --- L4: User Preferences ---
    profile_block = _build_profile_block(context)
    if profile_block:
        blocks.append(profile_block)
        injected_layers.append("L4_profile")

    # --- L4: Business Context ---
    context_block = _build_context_block(context)
    if context_block:
        blocks.append(context_block)
        injected_layers.append("L4_context")

    # --- L4: Active Campaigns ---
    campaign_block = _build_campaigns_block(context)
    if campaign_block:
        blocks.append(campaign_block)
        injected_layers.append("L4_campaigns")

    # Combine L4 block and compute token usage
    l4_text = "\n\n".join(blocks)
    l4_tokens = _count_tokens(l4_text)
    remaining_budget = max_tokens - l4_tokens

    _L3_HEADER = "**Business Insights from past analyses:**\n"

    # --- L3: Recent Insights (higher priority — trimmed first before L2 is dropped) ---
    insight_lines: list[str] = []
    insight_ids: list[str] = []
    for ins in context.recent_insights[:inject_recent_insights]:
        if ins.confidence == "low":
            continue  # BR: low-confidence insights not injected
        insight_ids.append(ins.id)
        tags_str = ", ".join(ins.tags) if ins.tags else ""
        line = f"- [{ins.date}] {ins.topic}: {ins.conclusion}"
        if tags_str:
            line += f" ({tags_str})"
        insight_lines.append(line)

    l3_text = ""
    if insight_lines:
        l3_text = _L3_HEADER + "\n".join(insight_lines)
        l3_tokens = _count_tokens(l3_text)
        if l3_tokens <= remaining_budget:
            remaining_budget -= l3_tokens
            injected_layers.append("L3_insights")
            injected_insight_ids = insight_ids
        else:
            # Gradually reduce insights to fit (cutting order: L3 before L2)
            while insight_lines and _count_tokens(
                _L3_HEADER + "\n".join(insight_lines)
            ) > remaining_budget:
                insight_lines.pop()
                insight_ids = insight_ids[: len(insight_lines)]
            if insight_lines:
                l3_text = _L3_HEADER + "\n".join(insight_lines)
                remaining_budget -= _count_tokens(l3_text)
                injected_layers.append("L3_insights")
                injected_insight_ids = insight_ids
            else:
                l3_text = ""

    # --- L2: Recent Session Summaries (cut entirely only after L3 is maximally trimmed) ---
    summary_lines: list[str] = []
    summary_ids: list[str] = []
    for s in context.recent_summaries[:inject_recent_summaries]:
        summary_ids.append(s.session_id)
        summary_lines.append(f"- [{s.date}] {s.summary}")

    l2_text = ""
    if summary_lines:
        l2_text = "**Recent Session Context:**\n" + "\n".join(summary_lines)
        l2_tokens = _count_tokens(l2_text)
        if l2_tokens <= remaining_budget:
            injected_layers.append("L2_summaries")
            injected_summary_ids = summary_ids
        else:
            l2_text = ""  # cut L2 entirely if still over budget after L3 trimming

    # Assemble final memory header (L4 → L3 → L2 order for readability)
    memory_parts = [p for p in [l4_text, l3_text, l2_text] if p]
    if not memory_parts:
        if on_inject:
            on_inject([], 0, [], [])
        return base_prompt

    memory_header = (
        "## Your Personalized Context\n"
        + "\n\n".join(memory_parts)
        + "\n\n---\n"
    )
    total_memory_tokens = _count_tokens(memory_header)

    if on_inject:
        on_inject(injected_layers, total_memory_tokens, injected_insight_ids, injected_summary_ids)

    return memory_header + base_prompt


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------


def _build_profile_block(ctx: MemoryContext) -> str:
    p = ctx.user_profile
    lines = []

    if p.role and p.role != "operations":
        lines.append(f"User role: {p.role}")

    a = p.analysis
    if a.default_period and a.default_period != "7d":
        lines.append(f"Default analysis period: {a.default_period}")
    if a.preferred_dimensions:
        lines.append(f"Preferred analysis dimensions: {', '.join(a.preferred_dimensions)}")
    if a.key_metrics:
        lines.append(f"Key metrics to focus on: {', '.join(a.key_metrics)}")
    if a.rfm_focus:
        lines.append(f"RFM segments of interest: {', '.join(a.rfm_focus)}")

    o = p.output
    if o.format and o.format != "table":
        lines.append(f"Preferred output format: {o.format}")
    if o.show_yoy:
        lines.append("Always include year-over-year comparison")

    s = p.scope
    if s.channels:
        lines.append(f"Scope — channels: {', '.join(s.channels)}")
    if s.provinces:
        lines.append(f"Scope — provinces: {', '.join(s.provinces)}")

    if not lines:
        return ""
    return "**User Preferences:**\n" + "\n".join(f"- {line}" for line in lines)


def _build_context_block(ctx: MemoryContext) -> str:
    bc = ctx.business_context
    lines = []

    if bc.industry:
        lines.append(f"Industry: {bc.industry}")
    if bc.peak_seasons:
        lines.append(f"Peak seasons: {', '.join(bc.peak_seasons)}")
    if bc.kpi_baselines:
        baselines = ", ".join(f"{k}={v}" for k, v in bc.kpi_baselines.items())
        lines.append(f"KPI baselines: {baselines}")

    if not lines:
        return ""
    return "**Business Context:**\n" + "\n".join(f"- {l}" for l in lines)


def _build_campaigns_block(ctx: MemoryContext) -> str:
    """BR-02: only active (non-archived) campaigns are injected."""
    active = ctx.active_campaigns
    if not active:
        return ""
    lines = []
    for c in active:
        line = f"- [{c.period.start}~{c.period.end}] {c.name}"
        if c.effect_summary:
            line += f" — {c.effect_summary}"
        lines.append(line)
    return "**Ongoing/Recent Campaigns (for context):**\n" + "\n".join(lines)
