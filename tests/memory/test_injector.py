"""Tests for cli/memory/injector.py."""

import pytest
from cli.memory.injector import _count_tokens, build_system_prompt
from cli.memory.models import (
    Campaign,
    CampaignPeriod,
    Insight,
    MemoryContext,
    SessionSummary,
    UserProfile,
)

BASE = "You are the assistant."


def _make_context_with_prefs() -> MemoryContext:
    ctx = MemoryContext()
    ctx.user_profile.analysis.default_period = "30d"
    ctx.user_profile.analysis.preferred_dimensions = ["channel"]
    return ctx


class TestBuildSystemPrompt:
    def test_empty_context_returns_base(self):
        ctx = MemoryContext()
        result = build_system_prompt(ctx, BASE)
        assert result == BASE

    def test_preferences_injected(self):
        ctx = _make_context_with_prefs()
        result = build_system_prompt(ctx, BASE)
        assert "30d" in result or "channel" in result
        assert BASE in result

    def test_archived_campaigns_not_injected(self):
        ctx = MemoryContext()
        ctx.user_profile.analysis.preferred_dimensions = ["channel"]
        ctx.campaigns = [
            Campaign(
                id="old",
                name="Old Campaign",
                period=CampaignPeriod(start="2020-01-01", end="2020-12-31"),
            )
        ]
        result = build_system_prompt(ctx, BASE)
        assert "Old Campaign" not in result

    def test_active_campaigns_injected(self):
        ctx = MemoryContext()
        ctx.user_profile.analysis.preferred_dimensions = ["channel"]
        ctx.campaigns = [
            Campaign(
                id="act",
                name="Current Campaign",
                period=CampaignPeriod(start="2099-01-01", end="2099-12-31"),
            )
        ]
        result = build_system_prompt(ctx, BASE)
        assert "Current Campaign" in result

    def test_low_confidence_insights_not_injected(self):
        ctx = _make_context_with_prefs()
        ctx.recent_insights = [
            Insight(
                id="2026-04-01-test",
                date="2026-04-01",
                topic="Low confidence",
                conclusion="uncertain finding",
                confidence="low",
            )
        ]
        result = build_system_prompt(ctx, BASE)
        assert "uncertain finding" not in result

    def test_medium_confidence_injected(self):
        ctx = _make_context_with_prefs()
        ctx.recent_insights = [
            Insight(
                id="2026-04-01-medium",
                date="2026-04-01",
                topic="Medium confidence",
                conclusion="medium finding",
                confidence="medium",
            )
        ]
        result = build_system_prompt(ctx, BASE)
        assert "medium finding" in result

    def test_token_budget_respected(self):
        ctx = _make_context_with_prefs()
        # Add many insights to trigger budget overflow
        ctx.recent_insights = [
            Insight(
                id=f"2026-04-01-ins{i}",
                date="2026-04-01",
                topic=f"Topic {i}",
                conclusion="A " * 200,  # ~50 tokens each
                confidence="high",
            )
            for i in range(20)
        ]
        result = build_system_prompt(ctx, BASE, max_tokens=500)
        tokens = _count_tokens(result) - _count_tokens(BASE)
        assert tokens <= 600  # some tolerance for the header lines

    def test_on_inject_callback_called(self):
        ctx = _make_context_with_prefs()
        cb_args = {}

        def on_inject(layers, token_count, insight_ids, summary_ids):
            cb_args["layers"] = layers
            cb_args["tokens"] = token_count

        build_system_prompt(ctx, BASE, on_inject=on_inject)
        assert "layers" in cb_args
        assert cb_args["tokens"] > 0

    def test_on_inject_called_with_empty_layers_on_empty_context(self):
        ctx = MemoryContext()
        cb_args = {}

        def on_inject(layers, token_count, insight_ids, summary_ids):
            cb_args["layers"] = layers
            cb_args["tokens"] = token_count

        build_system_prompt(ctx, BASE, on_inject=on_inject)
        # on_inject is called with empty layers and 0 tokens for empty context
        assert cb_args.get("layers") == []
        assert cb_args.get("tokens") == 0
